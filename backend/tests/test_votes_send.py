import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import (
    audit_logs_table,
    get_engine,
    hash_identifier,
    identities_table,
    init_db,
    reset_db,
    votes_table,
    create_question,
)
from app.main import app


@pytest.mark.anyio
async def test_send_vote_stores_ciphertext_and_audit():
    engine = get_engine()
    await init_db(engine)
    await reset_db(engine)

    participant = f"participant-{uuid.uuid4()}"
    agent = f"agent-{uuid.uuid4()}"
    question_id = "Q1"
    await create_question(engine, question_id=question_id, label="test", created_by="test")
    ciphertext = "ciphertext-demo"
    key_id = "key-v1"

    payload = {
        "question_id": question_id,
        "participant_id": participant,
        "agent_id": agent,
        "ciphertext": ciphertext,
        "key_id": key_id,
    }

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/votes/send", json=payload)

    assert response.status_code == 201, "POST /votes/send should return 201"
    body = response.json()
    assert body["status"] == "stored", "Response should acknowledge storage"
    assert body["question_id"] == question_id, "Echoed question_id must match input"
    assert body["key_id"] == key_id, "Echoed key_id must match input"

    p_hash = hash_identifier(participant)

    async with engine.connect() as conn:
        vote_row = (
            await conn.execute(
                select(votes_table).where(votes_table.c.participant_hash == p_hash)
            )
        ).mappings().first()
        identity_row = (
            await conn.execute(
                select(identities_table).where(identities_table.c.participant_hash == p_hash)
            )
        ).mappings().first()
        audit_row = (
            await conn.execute(select(audit_logs_table).order_by(audit_logs_table.c.id.desc()).limit(1))
        ).mappings().first()

    assert vote_row is not None, "Vote row must exist in votes schema"
    assert vote_row["ciphertext"] == ciphertext, "Ciphertext must be stored as provided"
    assert vote_row["key_id"] == key_id, "Key identifier must be persisted"
    assert identity_row["agent_hash"] == hash_identifier(agent), "Agent hash must match input"
    assert audit_row["event_type"] == "vote_received", "Audit log must capture the event"
    assert audit_row["payload_hash"], "Audit entry must include payload hash"
