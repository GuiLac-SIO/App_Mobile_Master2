import uuid

import pytest
from httpx import AsyncClient

from app.crypto.paillier import decrypt, encrypt
from app.db import get_engine, init_db, reset_db, create_question
from app.main import DEMO_KEY_ID, app, get_demo_keypair


@pytest.mark.anyio
async def test_aggregate_votes_homomorphic_sum():
    engine = get_engine()
    await init_db(engine)
    await reset_db(engine)

    pub, priv = get_demo_keypair()
    question_id = "Q-agg"
    await create_question(engine, question_id=question_id, label="test", created_by="test")

    c1 = encrypt(pub, 1)
    c2 = encrypt(pub, 1)

    payloads = [
        {
            "question_id": question_id,
            "participant_id": f"participant-{uuid.uuid4()}",
            "agent_id": f"agent-{uuid.uuid4()}",
            "ciphertext": str(c1),
            "key_id": DEMO_KEY_ID,
        },
        {
            "question_id": question_id,
            "participant_id": f"participant-{uuid.uuid4()}",
            "agent_id": f"agent-{uuid.uuid4()}",
            "ciphertext": str(c2),
            "key_id": DEMO_KEY_ID,
        },
    ]

    async with AsyncClient(app=app, base_url="http://test") as client:
        for payload in payloads:
            resp = await client.post("/votes/send", json=payload)
            assert resp.status_code == 201

        agg_resp = await client.get(
            "/votes/aggregate",
            params={"question_id": question_id, "key_id": DEMO_KEY_ID},
        )

    assert agg_resp.status_code == 200
    body = agg_resp.json()
    assert body["question_id"] == question_id
    assert body["key_id"] == DEMO_KEY_ID
    assert body["count"] == 2
    assert body["total"] == 2

    agg_ct = int(body["aggregate_ciphertext"])
    assert decrypt(priv, agg_ct) == 2


@pytest.mark.anyio
async def test_aggregate_no_votes_returns_zero():
    engine = get_engine()
    await init_db(engine)
    await reset_db(engine)

    question_id = "Q-empty"
    async with AsyncClient(app=app, base_url="http://test") as client:
        agg_resp = await client.get(
            "/votes/aggregate",
            params={"question_id": question_id, "key_id": DEMO_KEY_ID},
        )

    assert agg_resp.status_code == 200
    body = agg_resp.json()
    assert body["count"] == 0
    assert body["total"] == 0
    assert body["aggregate_ciphertext"] is None
