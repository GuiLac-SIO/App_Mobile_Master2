import pytest

from app.db import get_engine, init_db, reset_db, verify_db_permissions


@pytest.mark.anyio
async def test_db_role_is_not_privileged_and_has_needed_grants():
    engine = get_engine()
    await init_db(engine)
    await reset_db(engine)

    perms = await verify_db_permissions(engine)

    assert perms["rolsuper"] is False
    assert perms["rolcreatedb"] is False
    assert perms["rolcreaterole"] is False
    assert perms["rolreplication"] is False

    assert perms["can_insert_votes"] is True
    assert perms["can_select_votes"] is True
    assert perms["can_select_identities"] is True
