"""Tests for POST /api/me/positions/fills."""

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import get_current_user
from src.api.main import app
from src.core.database import get_session
from src.core.models import Instrument, User
from src.positions.repository import record_position_fill


@pytest.fixture
async def pos_user(session):
    u = User(username="manual_fill_user")
    session.add(u)
    await session.flush()
    return u


@pytest.fixture
async def client(session, pos_user):
    async def _override():
        yield session

    async def _user_override():
        return pos_user

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_current_user] = _user_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_manual_fill_creates_position(client: AsyncClient, session, pos_user):
    response = await client.post(
        "/api/me/positions/fills",
        json={"symbol": "aapl", "quantity": 10, "fill_price": 150.5, "side": "buy"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["symbol"] == "AAPL"
    assert data["quantity"] == 10.0
    assert data["avg_cost"] == 150.5

    list_resp = await client.get("/api/me/positions/")
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["quantity"] == 10.0


async def test_manual_fill_weighted_avg_on_add(client: AsyncClient, session, pos_user):
    inst = Instrument(symbol="MSFT", type="stock")
    session.add(inst)
    await session.flush()
    await record_position_fill(
        session,
        user_id=pos_user.id,
        instrument_id=inst.id,
        side="buy",
        quantity=Decimal("10"),
        fill_price=Decimal("100"),
    )
    await session.flush()

    response = await client.post(
        "/api/me/positions/fills",
        json={"symbol": "MSFT", "quantity": 10, "fill_price": 120, "side": "buy"},
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 20.0
    assert response.json()["avg_cost"] == 110.0


async def test_manual_fill_sell_rejects_without_position(client: AsyncClient):
    response = await client.post(
        "/api/me/positions/fills",
        json={"symbol": "GOOG", "quantity": 1, "fill_price": 100, "side": "sell"},
    )
    assert response.status_code == 400
