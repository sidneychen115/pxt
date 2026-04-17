import logging
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import async_session_factory
from src.core.models import TradeSignalRecord, Instrument, Option
from src.signals.notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)


def _get_notifier() -> BaseNotifier:
    from src.signals.notifiers.email import EmailNotifier
    return EmailNotifier()
    # Phase 2: return SchwabTrader() when settings.notifier == "schwab"


class SignalProcessor:
    async def process_pending(self) -> int:
        """Process all pending signals. Returns count processed."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(TradeSignalRecord)
                .where(TradeSignalRecord.status == "pending")
                .order_by(TradeSignalRecord.created_at)
                .limit(50)
            )
            signals = result.scalars().all()
            session.expunge_all()  # detach safely before session closes

        processed = 0
        notifier = _get_notifier()
        for signal in signals:
            symbol = await self._get_symbol(signal)
            success = await notifier.send(signal, symbol)
            new_status = "notified" if success else "pending"
            async with async_session_factory() as session:
                await session.execute(
                    update(TradeSignalRecord)
                    .where(TradeSignalRecord.id == signal.id)
                    .values(status=new_status)
                )
                await session.commit()
            if success:
                processed += 1
                logger.info("Signal %d notified for %s", signal.id, symbol)
        return processed

    async def _get_symbol(self, signal: TradeSignalRecord) -> str:
        async with async_session_factory() as session:
            if signal.stock_id:
                result = await session.execute(
                    select(Instrument.symbol).where(Instrument.id == signal.stock_id)
                )
                return result.scalar_one_or_none() or "UNKNOWN"
            if signal.option_id:
                result = await session.execute(
                    select(Option.symbol).where(Option.id == signal.option_id)
                )
                return result.scalar_one_or_none() or "UNKNOWN"
        return "UNKNOWN"
