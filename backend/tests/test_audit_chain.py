import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.db import audit_logs_table, get_engine, init_db, reset_db, verify_hash_chain
from app.main import app


@pytest.mark.anyio
async def test_audit_chain_ok():
    engine = get_engine()
    await init_db(engine)
    await reset_db(engine)

    payload = {
        "question_id": "Q-audit",
        "participant_id": f"p-{uuid.uuid4()}",
        "agent_id": f"a-{uuid.uuid4()}",
        "ciphertext": "123",
        "key_id": "key-v1",
    }

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/votes/send", json=payload)
        assert resp.status_code == 201

    result = await verify_hash_chain(engine)
    assert result["ok"] is True
    assert result["broken_id"] is None
    assert result["length"] >= 1


@pytest.mark.anyio
async def test_audit_chain_detects_corruption():
    engine = get_engine()
    await init_db(engine)
    await reset_db(engine)

    # create two audit entries via two votes
    async with AsyncClient(app=app, base_url="http://test") as client:
        for i in range(2):
            payload = {
                "question_id": f"Q-corrupt-{i}",
                "participant_id": f"p-{uuid.uuid4()}",
                "agent_id": f"a-{uuid.uuid4()}",
                "ciphertext": str(100 + i),
                "key_id": "key-v1",
            }
            resp = await client.post("/votes/send", json=payload)
            assert resp.status_code == 201

    # corrupt the second audit entry's prev_hash
    async with engine.begin() as conn:
        await conn.execute(
            update(audit_logs_table)
            .where(audit_logs_table.c.id == 2)
            .values(prev_hash="bogus")
        )

    result = await verify_hash_chain(engine)
    assert result["ok"] is False
    assert result["broken_id"] == 2
