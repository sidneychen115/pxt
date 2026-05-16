import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_signals_require_user(client):
    r = await client.get("/api/signals/")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_users_public(client):
    r = await client.get("/api/auth/users")
    assert r.status_code in (200, 500)
