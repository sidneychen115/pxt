import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from src.core.config import settings
from src.core.database import async_session_factory
from src.core.models import Strategy, SystemEvent
from src.strategies.live_context import LiveDataContext
from src.strategies.registry import REGISTRY, discover_strategies
from src.data.collector import DataCollector

logger = logging.getLogger(__name__)
TZ = ZoneInfo(settings.timezone)


class _SignalProcessorStub:
    async def process_pending(self) -> None:
        pass  # will be replaced by SignalProcessor in Phase D


class StrategyScheduler:
    def __init__(self):
        self._scheduler = AsyncIOScheduler(timezone=str(TZ))
        self._collector = DataCollector()
        self._signal_processor = _SignalProcessorStub()

    async def start(self) -> None:
        discover_strategies()
        await self._register_all_jobs()
        self._scheduler.start()
        logger.info("Scheduler started.")

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)

    async def _register_all_jobs(self) -> None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.is_active.is_(True))
            )
            strategies = result.scalars().all()

        # Data sync job: runs every 5 minutes during market hours (CT)
        self._scheduler.add_job(
            self._run_data_sync,
            CronTrigger(minute="*/5", hour="8-15", day_of_week="mon-fri", timezone=TZ),
            id="data_sync",
            replace_existing=True,
        )

        # Signal processor: runs every minute
        self._scheduler.add_job(
            self._run_signal_processor,
            CronTrigger(minute="*", timezone=TZ),
            id="signal_processor",
            replace_existing=True,
        )

        for config in strategies:
            await self._register_strategy_job(config)

    async def _register_strategy_job(self, config: Strategy) -> None:
        if config.id not in REGISTRY:
            logger.warning("Strategy '%s' in DB but not in registry — skipping.", config.id)
            return
        self._scheduler.add_job(
            self._run_strategy,
            CronTrigger.from_crontab(config.run_frequency, timezone=TZ),
            kwargs={"strategy_id": config.id},
            id=f"strategy_{config.id}",
            replace_existing=True,
        )
        logger.info("Registered strategy job: %s @ %s", config.id, config.run_frequency)

    async def reload_strategy(self, strategy_id: str) -> None:
        """Hot-reload a single strategy job after config change."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            config = result.scalar_one_or_none()
        if config and config.is_active:
            await self._register_strategy_job(config)
        else:
            try:
                self._scheduler.remove_job(f"strategy_{strategy_id}")
            except Exception:
                pass

    async def _run_data_sync(self) -> None:
        try:
            await self._collector.run_full_sync()
        except Exception as e:
            await self._log_event("data_sync", "error", str(e))

    async def _run_signal_processor(self) -> None:
        try:
            await self._signal_processor.process_pending()
        except Exception as e:
            await self._log_event("signal_processor", "error", str(e))

    async def _run_strategy(self, strategy_id: str) -> None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            config = result.scalar_one_or_none()
            if not config:
                return

            strategy = REGISTRY[strategy_id]()
            ctx = LiveDataContext(session)
            try:
                async with asyncio.timeout(settings.strategy_run_timeout):
                    signals = await strategy.generate_signals(
                        config.symbols, config.parameters, ctx
                    )
                await self._save_signals(session, config, signals)
                await self._log_event(
                    "strategy_run", "info",
                    f"Strategy {strategy_id} generated {len(signals)} signal(s).",
                    session=session,
                )
            except TimeoutError:
                await self._log_event(
                    "strategy_run", "error",
                    f"Strategy {strategy_id} timed out after {settings.strategy_run_timeout}s.",
                    session=session,
                )
            except Exception as e:
                await self._log_event(
                    "strategy_run", "error",
                    f"Strategy {strategy_id} failed: {e}",
                    session=session,
                )

    async def _save_signals(self, session, config: Strategy, signals) -> None:
        from src.core.models import TradeSignalRecord, Instrument
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy import select as sa_select
        now = datetime.now(timezone.utc)
        for sig in signals:
            inst_result = await session.execute(
                sa_select(Instrument.id).where(Instrument.symbol == sig.symbol)
            )
            stock_id = inst_result.scalar_one_or_none()
            if stock_id is None:
                continue
            stmt = pg_insert(TradeSignalRecord).values(
                strategy_id=config.id,
                stock_id=stock_id,
                signal_time=now,
                direction=sig.direction,
                order_type=sig.order_type,
                quantity=sig.quantity,
                limit_price=sig.limit_price,
                stop_price=sig.stop_price,
                confidence=sig.confidence,
                reasoning=sig.reasoning,
                status="pending",
            ).on_conflict_do_nothing()
            await session.execute(stmt)
        await session.commit()

    async def _log_event(
        self, event_type: str, level: str, message: str, session=None
    ) -> None:
        close_after = session is None
        if session is None:
            session = async_session_factory()
            await session.__aenter__()
        try:
            session.add(SystemEvent(event_type=event_type, level=level, message=message))
            await session.commit()
        finally:
            if close_after:
                await session.__aexit__(None, None, None)
        if level == "error":
            logger.error("[%s] %s", event_type, message)
        else:
            logger.info("[%s] %s", event_type, message)
