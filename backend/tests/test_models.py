import pytest
from sqlalchemy import select
from src.core.models import Instrument, Strategy


async def test_instrument_create(session):
    inst = Instrument(symbol="AAPL", type="stock", exchange="NASDAQ", name="Apple Inc.")
    session.add(inst)
    await session.commit()
    result = await session.execute(select(Instrument).where(Instrument.symbol == "AAPL"))
    found = result.scalar_one()
    assert found.symbol == "AAPL"
    assert found.type == "stock"


async def test_strategy_create(session):
    s = Strategy(
        id="test_strat",
        name="Test",
        symbols=["AAPL"],
        timeframes=["1d"],
        run_frequency="0 16 * * 1-5",
    )
    session.add(s)
    await session.commit()
    result = await session.execute(select(Strategy).where(Strategy.id == "test_strat"))
    found = result.scalar_one()
    assert found.symbols == ["AAPL"]
