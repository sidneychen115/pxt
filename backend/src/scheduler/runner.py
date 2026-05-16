import asyncio
import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.engine.url import make_url

from src.core.config import settings
from src.core.database import async_session_factory
from src.core.models import SystemEvent, TradeSignalRecord, UserStrategy
from src.core.strategy_run_logger import StrategyRunLogger
from src.data.collector import DataCollector
from src.positions.repository import load_positions_by_symbol
from src.positions.service import filter_signals_for_positions
from src.scheduler.job_groups import (
    StrategyRunGroup,
    group_active_user_strategies,
    job_id_for_group,
    signals_for_user_symbols,
)
from src.scheduler.run_schedule import build_trigger, schedule_mode
from src.scheduler.timeframe_interval import anchor_timeframe
from src.signals.processor import SignalProcessor
from src.strategies.live_context import LiveDataContext
from src.strategies.base import PortfolioSnapshot
from src.strategies.registry import REGISTRY, discover_strategies

logger = logging.getLogger(__name__)
TZ = ZoneInfo(settings.timezone)

_LEGACY_JOB_RE = re.compile(r"^strategy_\d+_")

HA_MONTH_DAY_REVENUE_SLOTS_ID = "ha_month_day_revenue_slots"

# Snapshot runs: prefetch mark prices; avoid per-symbol DB OHLC pulls (heavy watchlists).
_PREFETCH_MARK_ONLY_STRATEGIES = frozenset(
    {"ha_month_week_band", HA_MONTH_DAY_REVENUE_SLOTS_ID}
)


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
                    select(UserStrategy).where(UserStrategy.is_active.is_(True))
                )
                user_strategies = result.scalars().all()
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
                    '(e.g. `ports: ["127.0.0.1:5432:5432"]` on the postgres service) and keep '
                    "DATABASE_URL pointing at localhost:5432. "
                    "Then recreate the container: `cd docker && docker compose up -d postgres`."
                ) from e
            raise

        self._scheduler.add_job(
            self._run_data_sync,
            CronTrigger(minute="*/5", hour="8-15", day_of_week="mon-fri", timezone=TZ),
            id="data_sync",
            replace_existing=True,
        )

        self._scheduler.add_job(
            self._run_signal_processor,
            CronTrigger(minute="*", timezone=TZ),
            id="signal_processor",
            replace_existing=True,
        )

        self._remove_legacy_per_user_jobs()
        for group in group_active_user_strategies(user_strategies):
            await self._register_strategy_group_job(group)

    def _remove_legacy_per_user_jobs(self) -> None:
        for job in self._scheduler.get_jobs():
            if _LEGACY_JOB_RE.match(job.id):
                try:
                    self._scheduler.remove_job(job.id)
                except Exception:
                    pass

    def _remove_group_jobs_for_strategy(self, strategy_id: str) -> None:
        prefix = f"strategy_grp_{strategy_id}_"
        for job in self._scheduler.get_jobs():
            if job.id.startswith(prefix):
                try:
                    self._scheduler.remove_job(job.id)
                except Exception:
                    pass

    async def _register_strategy_group_job(self, group: StrategyRunGroup) -> None:
        if group.strategy_id not in REGISTRY:
            logger.warning(
                "Strategy '%s' not in registry — skipping group (%s user(s)).",
                group.strategy_id,
                len(group.members),
            )
            return
        trigger = build_trigger(group.run_frequency, TZ)
        mode = schedule_mode(group.run_frequency)
        anchor_tf = anchor_timeframe(list(group.timeframes))
        jid = job_id_for_group(group)
        self._scheduler.add_job(
            self._run_strategy_group,
            trigger,
            kwargs={
                "strategy_id": group.strategy_id,
                "run_frequency": group.run_frequency,
                "parameters_json": group.parameters_json,
                "timeframes": list(group.timeframes),
            },
            id=jid,
            replace_existing=True,
        )
        logger.info(
            "Registered strategy group job: %s users=%s mode=%s frequency=%s "
            "(anchor TF %s, %s symbol(s))",
            group.strategy_id,
            [us.user_id for us in group.members],
            mode,
            group.run_frequency,
            anchor_tf,
            len(group.merged_symbols),
        )

    async def reload_user_strategy(self, user_id: int, strategy_id: str) -> None:
        await self._reregister_strategy_groups(strategy_id)

    async def reload_strategy(self, strategy_id: str) -> None:
        await self._reregister_strategy_groups(strategy_id)

    async def _reregister_strategy_groups(self, strategy_id: str) -> None:
        self._remove_legacy_per_user_jobs()
        self._remove_group_jobs_for_strategy(strategy_id)

        async with async_session_factory() as session:
            result = await session.execute(
                select(UserStrategy).where(
                    UserStrategy.strategy_id == strategy_id,
                    UserStrategy.is_active.is_(True),
                )
            )
            rows = result.scalars().all()

        for group in group_active_user_strategies(rows):
            await self._register_strategy_group_job(group)

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

    async def _load_strategy_group(
        self,
        strategy_id: str,
        run_frequency: str,
        parameters_json: str,
        timeframes: list[str],
    ) -> StrategyRunGroup | None:
        tf_key = tuple(sorted(timeframes))
        async with async_session_factory() as session:
            result = await session.execute(
                select(UserStrategy).where(
                    UserStrategy.strategy_id == strategy_id,
                    UserStrategy.is_active.is_(True),
                    UserStrategy.run_frequency == run_frequency,
                )
            )
            rows = result.scalars().all()

        for group in group_active_user_strategies(rows):
            if group.parameters_json == parameters_json and group.timeframes == tf_key:
                return group
        return None

    async def _run_strategy_group(
        self,
        strategy_id: str,
        run_frequency: str,
        parameters_json: str,
        timeframes: list[str],
    ) -> None:
        group = await self._load_strategy_group(
            strategy_id, run_frequency, parameters_json, timeframes
        )
        if not group:
            return

        async with async_session_factory() as session:
            run_log = StrategyRunLogger(session, strategy_id)
            mode = schedule_mode(group.run_frequency)
            strategy = REGISTRY[strategy_id]()
            run_params = dict(group.parameters)
            if group.timeframes:
                run_params.setdefault("timeframe", group.timeframes[0])
            use_snapshot = mode == "cron" or bool(
                run_params.get("snapshot_close_at_run", False)
            )
            merged_symbols = group.merged_symbols
            await run_log.start(
                f"Strategy {strategy_id} started (shared run, users {group.user_ids})",
                symbols=merged_symbols,
                timeframes=list(group.timeframes),
                schedule_mode=mode,
                run_frequency=group.run_frequency,
                snapshot_close=use_snapshot,
                user_ids=group.user_ids,
            )

            quote_prices: dict[str, float] = {}
            try:
                if use_snapshot:
                    if strategy_id not in _PREFETCH_MARK_ONLY_STRATEGIES:
                        for sym in merged_symbols:
                            for tf in group.timeframes or ["1d"]:
                                await run_log.step(f"Syncing OHLCV {sym} {tf}…")
                                await self._collector.sync_symbol_timeframe(sym, tf)
                    if strategy_id in _PREFETCH_MARK_ONLY_STRATEGIES:
                        sym_count = len(merged_symbols)
                        await run_log.step(
                            f"Prefetching mark prices for {sym_count} symbol(s)…"
                        )
                        from src.strategies.quote_batch import prefetch_mark_prices

                        quote_prices = await prefetch_mark_prices(merged_symbols)
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
                total_saved = 0
                all_signals = None
                async with asyncio.timeout(settings.strategy_run_timeout):
                    if strategy_id == HA_MONTH_DAY_REVENUE_SLOTS_ID:
                        for us in group.members:
                            positions_dec = await load_positions_by_symbol(
                                session, us.user_id
                            )
                            positions_live = {
                                sym: float(qty)
                                for sym, qty in positions_dec.items()
                                if float(qty) > 0
                            }
                            mv = 0.0
                            for sym, qty in positions_live.items():
                                px = quote_prices.get(sym)
                                if px is not None and px > 0:
                                    mv += qty * px
                            paper = float(
                                run_params.get("account_equity", 100_000.0)
                            )
                            equity_used = mv if mv > 0 else paper
                            pf_snap = PortfolioSnapshot(
                                equity=equity_used,
                                positions=positions_live,
                            )
                            user_raw = await strategy.generate_signals(
                                merged_symbols,
                                run_params,
                                ctx,
                                portfolio=pf_snap,
                            )
                            user_signals = signals_for_user_symbols(
                                user_raw, list(us.symbols or [])
                            )
                            user_signals = filter_signals_for_positions(
                                user_signals, positions_dec
                            )
                            await self._save_signals(session, us.user_id, us, user_signals)
                            total_saved += len(user_signals)
                            for sig in user_signals:
                                await run_log.step(
                                    f"User {us.user_id} signal {sig.symbol} "
                                    f"{sig.direction.upper()}: {sig.reasoning}",
                                    user_id=us.user_id,
                                    symbol=sig.symbol,
                                    direction=sig.direction,
                                )
                    else:
                        all_signals = await strategy.generate_signals(
                            merged_symbols, run_params, ctx, portfolio=None
                        )

                if strategy_id != HA_MONTH_DAY_REVENUE_SLOTS_ID:
                    total_saved = 0
                    assert all_signals is not None
                    for us in group.members:
                        user_signals = signals_for_user_symbols(
                            all_signals, list(us.symbols or [])
                        )
                        positions_dec = await load_positions_by_symbol(
                            session, us.user_id
                        )
                        user_signals = filter_signals_for_positions(
                            user_signals, positions_dec
                        )
                        await self._save_signals(session, us.user_id, us, user_signals)
                        total_saved += len(user_signals)
                        for sig in user_signals:
                            await run_log.step(
                                f"User {us.user_id} signal {sig.symbol} "
                                f"{sig.direction.upper()}: {sig.reasoning}",
                                user_id=us.user_id,
                                symbol=sig.symbol,
                                direction=sig.direction,
                            )

                await run_log.complete(
                    f"Strategy {strategy_id} finished — {total_saved} signal(s) "
                    f"across {len(group.members)} user(s)",
                    signal_count=total_saved,
                    user_ids=group.user_ids,
                )
            except TimeoutError:
                await run_log.fail(
                    f"Strategy {strategy_id} timed out after "
                    f"{settings.strategy_run_timeout}s",
                )
            except Exception as e:
                await run_log.fail(f"Strategy {strategy_id} failed: {e}")

    async def _save_signals(
        self, session, user_id: int, config: UserStrategy, signals
    ) -> None:
        from src.core.models import Instrument
        from sqlalchemy import select as sa_select

        now = datetime.now(timezone.utc)
        for sig in signals:
            inst_result = await session.execute(
                sa_select(Instrument.id).where(Instrument.symbol == sig.symbol)
            )
            stock_id = inst_result.scalar_one_or_none()
            if stock_id is None:
                continue
            session.add(
                TradeSignalRecord(
                    user_id=user_id,
                    strategy_id=config.strategy_id,
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
                    created_at=now,
                )
            )
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
        now = datetime.now(timezone.utc)
        if session is not None:
            session.add(
                SystemEvent(
                    event_type=event_type,
                    level=level,
                    message=message,
                    details=payload,
                    created_at=now,
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
                        created_at=now,
                    )
                )
                await s.commit()
        if level == "error":
            logger.error("[%s] %s", event_type, message)
        else:
            logger.info("[%s] %s", event_type, message)
