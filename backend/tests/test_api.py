import pytest
from httpx import AsyncClient, ASGITransport
from src.api.main import app
from src.core.database import get_session


@pytest.fixture
async def client(session):
    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_health(client: AsyncClient):
    response = await client.get("/api/system/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_list_strategies_empty(client: AsyncClient):
    response = await client.get("/api/strategies/")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_signals_empty(client: AsyncClient):
    response = await client.get("/api/signals/")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_signal_runs_empty(client: AsyncClient):
    response = await client.get("/api/signals/runs")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_backtests_empty(client: AsyncClient):
    response = await client.get("/api/backtests/")
    assert response.status_code == 200
    assert response.json() == []


async def test_get_strategy_404(client: AsyncClient):
    response = await client.get("/api/strategies/nonexistent")
    assert response.status_code == 404
