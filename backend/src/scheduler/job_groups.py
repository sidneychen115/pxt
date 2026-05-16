"""Group active user strategies so one scheduler job can serve multiple users."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from src.core.models import UserStrategy


@dataclass(frozen=True)
class StrategyRunGroup:
    strategy_id: str
    run_frequency: str
    parameters_json: str
    timeframes: tuple[str, ...]
    members: tuple[UserStrategy, ...]

    @property
    def parameters(self) -> dict:
        return json.loads(self.parameters_json)

    @property
    def merged_symbols(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for us in self.members:
            for sym in us.symbols or []:
                if sym not in seen:
                    seen.add(sym)
                    out.append(sym)
        return out

    @property
    def user_ids(self) -> list[int]:
        return [us.user_id for us in self.members]


def _parameters_json(parameters: dict | None) -> str:
    return json.dumps(parameters or {}, sort_keys=True, separators=(",", ":"))


def _group_key(us: UserStrategy) -> tuple[str, str, str, tuple[str, ...]]:
    return (
        us.strategy_id,
        us.run_frequency,
        _parameters_json(us.parameters),
        tuple(sorted(us.timeframes or [])),
    )


def group_active_user_strategies(rows: list[UserStrategy]) -> list[StrategyRunGroup]:
    """Merge rows that share strategy, schedule, parameters, and timeframes."""
    buckets: dict[tuple[str, str, str, tuple[str, ...]], list[UserStrategy]] = {}
    for us in rows:
        if not us.is_active:
            continue
        key = _group_key(us)
        buckets.setdefault(key, []).append(us)

    groups: list[StrategyRunGroup] = []
    for (strategy_id, run_frequency, parameters_json, timeframes), members in buckets.items():
        groups.append(
            StrategyRunGroup(
                strategy_id=strategy_id,
                run_frequency=run_frequency,
                parameters_json=parameters_json,
                timeframes=timeframes,
                members=tuple(members),
            )
        )
    return groups


def job_id_for_group(group: StrategyRunGroup) -> str:
    payload = (
        f"{group.strategy_id}\0{group.run_frequency}\0"
        f"{group.parameters_json}\0{','.join(group.timeframes)}"
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
    return f"strategy_grp_{group.strategy_id}_{digest}"


def signals_for_user_symbols(signals: list, user_symbols: list[str]) -> list:
    allowed = set(user_symbols or [])
    if not allowed:
        return []
    return [s for s in signals if s.symbol in allowed]
