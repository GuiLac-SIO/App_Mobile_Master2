"""Shared pytest fixtures for the Secure Votes test suite."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import get_engine, init_db, reset_db
from app.main import app


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture()
async def engine():
    """Provide a ready-to-use async engine with clean tables."""
    eng = get_engine()
    await init_db(eng)
    await reset_db(eng)
    return eng


@pytest.fixture()
async def client():
    """Provide an async HTTP test client bound to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
