"""Strategy update API (max_symbols enforcement)."""

import pytest
from httpx import AsyncClient

from src.core.models import Strategy


@pytest.fixture
async def ha_strategy(session):
    row = Strategy(
        id="ha_month_week_band",
        name="HA Month Open vs Weekly Close (band)",
        description="test",
        is_active=False,
        symbols=["SPY"],
        timeframes=["1d"],
        run_frequency="0 14 * * mon-fri",
        parameters={},
        max_symbols=200,
    )
    session.add(row)
    await session.commit()
    return row


async def test_update_strategy_symbols_within_max(client: AsyncClient, ha_strategy):
    syms = [f"SYM{i}" for i in range(10)]
    response = await client.put(
        "/api/strategies/ha_month_week_band",
        json={"symbols": syms},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_update_strategy_symbols_exceeds_max(client: AsyncClient, ha_strategy):
    syms = [f"SYM{i}" for i in range(201)]
    response = await client.put(
        "/api/strategies/ha_month_week_band",
        json={"symbols": syms},
    )
    assert response.status_code == 400
    assert "max_symbols" in response.json()["detail"]


async def test_update_strategy_uses_row_max_not_hardcoded_50(
    client: AsyncClient, session, ha_strategy
):
    """When DB max_symbols is 80, 60 symbols should succeed (old code used 50)."""
    ha_strategy.max_symbols = 80
    await session.commit()

    syms = [f"SYM{i}" for i in range(60)]
    response = await client.put(
        "/api/strategies/ha_month_week_band",
        json={"symbols": syms},
    )
    assert response.status_code == 200
