import pytest
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from src.core.models import Instrument, Strategy, TradeSignalRecord
from src.signals.processor import SignalProcessor


def _make_session_factory(session):
    """Return a context-manager factory that always yields the shared test session."""
    @asynccontextmanager
    async def _factory():
        yield session
    return _factory


def _make_strategy(session):
    """Helper to create and persist a minimal Strategy row."""
    s = Strategy(
        id="test_strat",
        name="Test Strategy",
        symbols=["AAPL"],
        timeframes=["1d"],
        run_frequency="0 16 * * 1-5",
    )
    session.add(s)
    return s


async def test_process_pending_sends_notification(session):
    """process_pending() returns 1 and sets status='notified' when send() succeeds."""
    _make_strategy(session)
    inst = Instrument(symbol="AAPL", type="stock")
    session.add(inst)
    await session.flush()

    signal = TradeSignalRecord(
        strategy_id="test_strat",
        stock_id=inst.id,
        signal_time=datetime.now(timezone.utc),
        direction="buy",
        order_type="market",
        status="pending",
    )
    session.add(signal)
    await session.flush()

    factory = _make_session_factory(session)
    mock_send = AsyncMock(return_value=True)

    with (
        patch("src.signals.processor.async_session_factory", factory),
        patch("src.signals.notifiers.email.EmailNotifier.send", mock_send),
    ):
        processor = SignalProcessor()
        count = await processor.process_pending()

    assert count == 1
    mock_send.assert_called_once()

    # Verify DB status was updated to "notified"
    await session.refresh(signal)
    assert signal.status == "notified"


async def test_process_pending_keeps_pending_on_failure(session):
    """process_pending() returns 0 and leaves status='pending' when send() fails."""
    _make_strategy(session)
    inst = Instrument(symbol="TSLA", type="stock")
    session.add(inst)
    await session.flush()

    signal = TradeSignalRecord(
        strategy_id="test_strat",
        stock_id=inst.id,
        signal_time=datetime.now(timezone.utc),
        direction="sell",
        order_type="market",
        status="pending",
    )
    session.add(signal)
    await session.flush()

    factory = _make_session_factory(session)
    mock_send = AsyncMock(return_value=False)

    with (
        patch("src.signals.processor.async_session_factory", factory),
        patch("src.signals.notifiers.email.EmailNotifier.send", mock_send),
    ):
        processor = SignalProcessor()
        count = await processor.process_pending()

    assert count == 0
    mock_send.assert_called_once()

    await session.refresh(signal)
    assert signal.status == "pending"


async def test_get_symbol_stock(session):
    """_get_symbol() returns the correct symbol for a stock-linked signal."""
    _make_strategy(session)
    inst = Instrument(symbol="MSFT", type="stock")
    session.add(inst)
    await session.flush()

    signal = TradeSignalRecord(
        strategy_id="test_strat",
        stock_id=inst.id,
        signal_time=datetime.now(timezone.utc),
        direction="buy",
        order_type="limit",
        status="pending",
    )
    session.add(signal)
    await session.flush()

    factory = _make_session_factory(session)

    with patch("src.signals.processor.async_session_factory", factory):
        processor = SignalProcessor()
        symbol = await processor._get_symbol(signal)

    assert symbol == "MSFT"
