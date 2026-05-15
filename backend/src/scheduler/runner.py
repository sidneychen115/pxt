import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.engine.url import make_url
from src.core.config import settings
from src.core.database import async_session_factory
from src.core.models import Strategy, SystemEvent
from src.core.strategy_run_logger import StrategyRunLogger
from src.strategies.live_context import LiveDataContext
from src.strategies.registry import REGISTRY, discover_strategies
from src.scheduler.run_schedule import build_trigger, schedule_mode
from src.scheduler.timeframe_interval import anchor_timeframe, min_interval_minutes
from src.data.collector import DataCollector
from src.signals.processor import SignalProcessor

logger = logging.getLogger(__name__)
TZ = ZoneInfo(settings.timezone)


class StrategyScheduler:
    def __init__(self):
        self._scheduler = AsyncIOScheduler(timezone=str(TZ))
        self._collector = DataCollector()
        self._signal_processor = SignalProcessor()

    async def start(self) -> None:
        discover_strategies()
        await self._register_all_jobs()
        self._scheduler.start()
        logger.info("Scheduler started.")

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)

    async def _register_all_jobs(self) -> None:
        parsed_url = None
        try:
            parsed_url = make_url(settings.database_url)
        except Exception:
            pass

        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(Strategy).where(Strategy.is_active.is_(True))
                )
                strategies = result.scalars().all()
        except OSError as e:
            if getattr(e, "errno", None) == 111 or isinstance(e, ConnectionRefusedError):
                target = (
                    f"{parsed_url.host}:{parsed_url.port}"
                    if parsed_url is not None and parsed_url.host
                    else "database"
                )
                raise RuntimeError(
                    f"Cannot connect to PostgreSQL at {target} (connection refused). "
                    "If the database runs only inside Docker, publish port 5432 to the host "
                    "(e.g. `ports: [\"127.0.0.1:5432:5432\"]` on the postgres service) and keep "
                    "DATABASE_URL pointing at localhost:5432. "
                    "Then recreate the container: `cd docker && docker compose up -d postgres`."
                ) from e
            raise

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
        trigger = build_trigger(config.run_frequency, TZ)
        mode = schedule_mode(config.run_frequency)
        anchor_tf = anchor_timeframe(list(config.timeframes or []))
        self._scheduler.add_job(
            self._run_strategy,
            trigger,
            kwargs={"strategy_id": config.id},
            id=f"strategy_{config.id}",
            replace_existing=True,
        )
        logger.info(
            "Registered strategy job: %s mode=%s frequency=%s (anchor TF %s)",
            config.id,
            mode,
            config.run_frequency,
            anchor_tf,
        )

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
                logger.debug("Job 'strategy_%s' not found in scheduler, nothing to remove.", strategy_id)

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

            run_log = StrategyRunLogger(session, strategy_id)
            mode = schedule_mode(config.run_frequency)
            strategy = REGISTRY[strategy_id]()
            run_params = dict(config.parameters or {})
            if config.timeframes:
                run_params.setdefault("timeframe", config.timeframes[0])
            use_snapshot = mode == "cron" or bool(
                run_params.get("snapshot_close_at_run", False)
            )
            await run_log.start(
                f"Strategy {strategy_id} started",
                symbols=list(config.symbols or []),
                timeframes=list(config.timeframes or []),
                schedule_mode=mode,
                run_frequency=config.run_frequency,
                snapshot_close=use_snapshot,
            )

            quote_prices: dict[str, float] = {}
            try:
                if use_snapshot:
                    # Do not sync before cron HA runs: yfinance may persist an intraday
                    # daily bar. Snapshot close exists only in memory (see LiveDataContext).
                    if strategy_id != "ha_month_week_band":
                        for sym in config.symbols:
                            for tf in config.timeframes or ["1d"]:
                                await run_log.step(f"Syncing OHLCV {sym} {tf}…")
                                await self._collector.sync_symbol_timeframe(sym, tf)
                    if strategy_id == "ha_month_week_band":
                        sym_count = len(config.symbols or [])
                        await run_log.step(
                            f"Prefetching mark prices for {sym_count} symbol(s)…"
                        )
                        from src.strategies.quote_batch import prefetch_mark_prices

                        quote_prices = await prefetch_mark_prices(config.symbols)
                        await run_log.step(
                            f"Mark prices ready: {len(quote_prices)}/{sym_count} symbol(s)",
                            quotes_ok=len(quote_prices),
                            quotes_total=sym_count,
                        )

                ctx = LiveDataContext(
                    session,
                    snapshot_close=use_snapshot,
                    quote_prices=quote_prices,
                    run_logger=run_log,
                )
                await run_log.step("Running generate_signals…")
                async with asyncio.timeout(settings.strategy_run_timeout):
                    signals = await strategy.generate_signals(
                        config.symbols, run_params, ctx, portfolio=None
                    )
                await self._save_signals(session, config, signals)
                for sig in signals:
                    await run_log.step(
                        f"Signal {sig.symbol} {sig.direction.upper()}: {sig.reasoning}",
                        symbol=sig.symbol,
                        direction=sig.direction,
                    )
                await run_log.complete(
                    f"Strategy {strategy_id} finished — {len(signals)} signal(s)",
                    signal_count=len(signals),
                )
            except TimeoutError:
                await run_log.fail(
                    f"Strategy {strategy_id} timed out after {settings.strategy_run_timeout}s",
                )
            except Exception as e:
                await run_log.fail(f"Strategy {strategy_id} failed: {e}")

    async def _save_signals(self, session, config: Strategy, signals) -> None:
        from src.core.models import TradeSignalRecord, Instrument
        from sqlalchemy import select as sa_select
        now = datetime.now(timezone.utc)
        for sig in signals:
            inst_result = await session.execute(
                sa_select(Instrument.id).where(Instrument.symbol == sig.symbol)
            )
            stock_id = inst_result.scalar_one_or_none()
            if stock_id is None:
                continue
            session.add(TradeSignalRecord(
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
            ))
        await session.commit()

    async def _log_event(
        self,
        event_type: str,
        level: str,
        message: str,
        session=None,
        *,
        details: dict | None = None,
    ) -> None:
        payload = details or {}
        if session is not None:
            session.add(
                SystemEvent(
                    event_type=event_type,
                    level=level,
                    message=message,
                    details=payload,
                )
            )
            await session.commit()
        else:
            async with async_session_factory() as s:
                s.add(
                    SystemEvent(
                        event_type=event_type,
                        level=level,
                        message=message,
                        details=payload,
                    )
                )
                await s.commit()
        if level == "error":
            logger.error("[%s] %s", event_type, message)
        else:
            logger.info("[%s] %s", event_type, message)
