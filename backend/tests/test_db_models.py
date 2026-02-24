import uuid

import pytest
from sqlalchemy import select

from app.db import (
    audit_logs_table,
    get_engine,
    hash_identifier,
    identities_table,
    init_db,
    reset_db,
    votes_table,
)


@pytest.mark.anyio
async def test_insert_and_read_separated_silos():
    engine = get_engine()
    await init_db(engine)
    await reset_db(engine)

    participant = f"participant-{uuid.uuid4()}"
    agent = f"agent-{uuid.uuid4()}"
    question_id = "Q1"

    p_hash = hash_identifier(participant)
    a_hash = hash_identifier(agent)
    ciphertext = "ciphertext-demo"
    key_id = "key-v1"
    payload_hash = hash_identifier("payload-demo")

    async with engine.begin() as conn:
        await conn.execute(
            identities_table.insert().values(
                participant_hash=p_hash,
                agent_hash=a_hash,
            )
        )
        await conn.execute(
            votes_table.insert().values(
                question_id=question_id,
                participant_hash=p_hash,
                ciphertext=ciphertext,
                key_id=key_id,
            )
        )
        await conn.execute(
            audit_logs_table.insert().values(
                event_type="test", payload_hash=payload_hash, prev_hash=None
            )
        )

    async with engine.connect() as conn:
        participant_row = (
            await conn.execute(
                select(identities_table).where(identities_table.c.participant_hash == p_hash)
            )
        ).mappings().first()
        vote_row = (
            await conn.execute(select(votes_table).where(votes_table.c.participant_hash == p_hash))
        ).mappings().first()
        audit_row = (await conn.execute(select(audit_logs_table))).mappings().first()

    assert participant_row["participant_hash"] == p_hash
    assert participant_row["agent_hash"] == a_hash

    assert vote_row["question_id"] == question_id
    assert vote_row["participant_hash"] == p_hash
    assert vote_row["ciphertext"] == ciphertext
    assert vote_row["key_id"] == key_id

    assert audit_row["event_type"] == "test"
    assert audit_row["payload_hash"] == payload_hash
    # prev_hash is None for first entry; later steps will chain
