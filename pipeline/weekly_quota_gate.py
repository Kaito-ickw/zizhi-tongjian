#!/usr/bin/env python3
"""Shared adaptive Claude weekly-quota gate for unattended ZZT jobs.

The provider exposes account-wide utilization, not usage by repository.  This
module samples utilization immediately before and after ZZT jobs.  Growth
between completed ZZT jobs is treated as other-project usage; growth during a
ZZT job is treated as this project's usage.  A short observation period runs
in shadow mode before enforcement starts.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STATE = Path("data/staging/zzt_weekly_quota_state.json")
OBSERVATION_HOURS = 48.0
FORECAST_MULTIPLIER = 1.25
SAFETY_RESERVE = 8.0
ABSOLUTE_CEILING = 92.0
RATE_WINDOW_HOURS = 48.0
DEFAULT_OTHER_DAILY = 5.0
DEFAULT_COSTS = {"drain": 4.0, "image": 0.75}
CLAUDE_CREDENTIALS = Path(
    os.environ.get("ZZT_CLAUDE_CREDENTIALS", "~/.claude/.credentials.json")
).expanduser()
TOKEN_MARGIN_SECONDS = 15 * 60
TOKEN_REFRESH_TIMEOUT = 240
TOKEN_REFRESH_CMD = os.environ.get(
    "ZZT_TOKEN_REFRESH_CMD", "claude -p ok --model haiku"
)


@dataclass(frozen=True)
class Quota:
    utilization: float
    resets_at: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def token_expires_at() -> float | None:
    """Return the credentials expiry as epoch seconds, or None if unreadable."""
    try:
        payload = json.loads(CLAUDE_CREDENTIALS.read_text(encoding="utf-8"))
        expires_at = payload["claudeAiOauth"]["expiresAt"]
        if isinstance(expires_at, bool):
            return None
        return float(expires_at) / 1000.0
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        return None


def ensure_claude_token(now: datetime) -> str:
    """Refresh an absent or nearly expired Claude token without raising errors."""
    try:
        expires_at = token_expires_at()
        threshold = now.timestamp() + TOKEN_MARGIN_SECONDS
        if expires_at is not None and expires_at > threshold:
            minutes = int((expires_at - now.timestamp()) / 60)
            return f"valid (expires in {minutes}m)"

        result = subprocess.run(
            shlex.split(TOKEN_REFRESH_CMD),
            timeout=TOKEN_REFRESH_TIMEOUT,
            capture_output=True,
            text=True,
        )
        expires_at = token_expires_at()
        if expires_at is not None and expires_at > threshold:
            minutes = int((expires_at - now.timestamp()) / 60)
            return f"refreshed (expires in {minutes}m)"
        return f"refresh-failed (exit={result.returncode})"
    except Exception as exc:
        return f"refresh-failed ({type(exc).__name__})"


def _oneline(text: str) -> str:
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "; ")
        .replace("|", "/")
    )


def quota_from_payload(payload: Any) -> Quota:
    if not isinstance(payload, list):
        raise ValueError("ai-quota response is not a provider array")
    claude = next(
        (item for item in payload if isinstance(item, dict) and item.get("provider") == "claude"),
        None,
    )
    if claude is None:
        raise ValueError("claude provider missing from ai-quota response")
    if claude.get("status") != "ok":
        detail = _oneline(str(claude.get("error", "")))[:200]
        raise ValueError(f"claude provider error: {detail}")
    seven = (claude.get("windows") or {}).get("seven_day") or {}
    utilization = seven.get("utilization")
    resets_at = seven.get("resets_at")
    if utilization is None or not resets_at:
        raise ValueError("claude seven_day utilization/resets_at unavailable")
    utilization = float(utilization)
    if not math.isfinite(utilization):
        raise ValueError("claude seven_day utilization is not finite")
    return Quota(utilization=utilization, resets_at=parse_time(str(resets_at)))


def read_live_quota() -> Quota:
    ensure_claude_token(utc_now())
    result = subprocess.run(
        ["ai-quota", "status", "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=45,
    )
    return quota_from_payload(json.loads(result.stdout))


def load_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def reset_state(reset_at: datetime, now: datetime) -> dict[str, Any]:
    return {
        "version": 1,
        "reset_at": iso_time(reset_at),
        "observed_since": iso_time(now),
        "last_completed": None,
        "external_intervals": [],
        "cost_estimates": dict(DEFAULT_COSTS),
        "active_run": None,
    }


def rollover_state(state: dict[str, Any], reset_at: datetime, now: datetime) -> dict[str, Any]:
    """Start a provider window without discarding cross-week rate learning."""
    fresh = reset_state(reset_at, now)
    fresh["observed_since"] = state.get("observed_since", fresh["observed_since"])
    fresh["external_intervals"] = trim_intervals(state.get("external_intervals", []), now)
    fresh["cost_estimates"].update(state.get("cost_estimates") or {})
    return fresh


def same_window(state: dict[str, Any], quota: Quota) -> bool:
    try:
        return abs((parse_time(state["reset_at"]) - quota.resets_at).total_seconds()) < 60
    except (KeyError, TypeError, ValueError):
        return False


def trim_intervals(intervals: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    cutoff = now.timestamp() - RATE_WINDOW_HOURS * 3600
    kept = []
    for interval in intervals:
        try:
            if parse_time(interval["end"]).timestamp() >= cutoff:
                kept.append(interval)
        except (KeyError, TypeError, ValueError):
            continue
    return kept


def external_rate(intervals: list[dict[str, Any]]) -> tuple[float, float]:
    points = 0.0
    hours = 0.0
    for interval in intervals:
        points += max(0.0, float(interval.get("points", 0.0)))
        hours += max(0.0, float(interval.get("hours", 0.0)))
    if hours <= 0:
        return DEFAULT_OTHER_DAILY, 0.0
    return points * 24.0 / hours, hours


def update_external_observation(
    state: dict[str, Any], quota: Quota, now: datetime
) -> None:
    last = state.get("last_completed")
    if not isinstance(last, dict):
        return
    try:
        start = parse_time(last["at"])
        start_utilization = float(last["utilization"])
    except (KeyError, TypeError, ValueError):
        return
    hours = max(0.0, (now - start).total_seconds() / 3600.0)
    if hours < 1 / 60:
        return
    state.setdefault("external_intervals", []).append(
        {
            "start": iso_time(start),
            "end": iso_time(now),
            "hours": hours,
            "points": max(0.0, quota.utilization - start_utilization),
        }
    )
    state["last_completed"] = None


def evaluate(
    state: dict[str, Any], quota: Quota, kind: str, now: datetime
) -> dict[str, Any]:
    intervals = trim_intervals(state.get("external_intervals", []), now)
    state["external_intervals"] = intervals
    other_daily, observed_hours = external_rate(intervals)
    days_left = max(0.0, (quota.resets_at - now).total_seconds() / 86400.0)
    forecast_other = other_daily * days_left * FORECAST_MULTIPLIER
    remaining = max(0.0, 100.0 - quota.utilization)
    available = remaining - forecast_other - SAFETY_RESERVE
    estimated_cost = float((state.get("cost_estimates") or {}).get(kind, DEFAULT_COSTS[kind]))
    observed_since = parse_time(state.get("observed_since", iso_time(now)))
    age_hours = max(0.0, (now - observed_since).total_seconds() / 3600.0)
    shadow = age_hours < OBSERVATION_HOURS or observed_hours < OBSERVATION_HOURS * 0.5
    below_hard_ceiling = quota.utilization + estimated_cost <= ABSOLUTE_CEILING
    permitted = below_hard_ceiling and available >= estimated_cost
    reason = (
        f"7d={quota.utilization:.1f}% remaining={remaining:.1f}pt; "
        f"other={other_daily:.2f}pt/day forecast={forecast_other:.1f}pt; "
        f"reserve={SAFETY_RESERVE:.1f}pt available={available:.1f}pt cost={estimated_cost:.2f}pt"
    )
    return {
        # Shadow mode bypasses only the forecast decision, never the hard cap.
        "verdict": "RUN" if below_hard_ceiling and (permitted or shadow) else "SKIP",
        "shadow": shadow,
        "would_verdict": "RUN" if permitted else "SKIP",
        "reason": reason,
        "estimated_cost": estimated_cost,
        "other_daily": other_daily,
        "observed_hours": observed_hours,
        "available": available,
    }


def begin(path: Path, kind: str, now: datetime, quota: Quota) -> dict[str, Any]:
    state = load_state(path)
    if not same_window(state, quota):
        state = rollover_state(state, quota.resets_at, now)
    # A killed job may never call complete.  Attribute the unknown interval to
    # other usage, conservatively, instead of disabling observations forever.
    active = state.get("active_run")
    if isinstance(active, dict):
        try:
            started = parse_time(active["started_at"])
            start_utilization = float(active["utilization"])
            hours = max(0.0, (now - started).total_seconds() / 3600.0)
            if hours >= 1 / 60:
                state.setdefault("external_intervals", []).append(
                    {
                        "start": iso_time(started),
                        "end": iso_time(now),
                        "hours": hours,
                        "points": max(0.0, quota.utilization - start_utilization),
                        "uncertain": True,
                    }
                )
        except (KeyError, TypeError, ValueError):
            pass
        state["active_run"] = None
    update_external_observation(state, quota, now)
    decision = evaluate(state, quota, kind, now)
    run_id = f"{kind}-{int(now.timestamp())}"
    if decision["verdict"] == "RUN":
        state["active_run"] = {
            "id": run_id,
            "kind": kind,
            "started_at": iso_time(now),
            "utilization": quota.utilization,
        }
    else:
        state["last_completed"] = {"at": iso_time(now), "utilization": quota.utilization}
        state["active_run"] = None
    save_state(path, state)
    decision["run_id"] = run_id if decision["verdict"] == "RUN" else ""
    return decision


def complete(path: Path, run_id: str, now: datetime, quota: Quota) -> dict[str, Any]:
    state = load_state(path)
    if not same_window(state, quota):
        state = rollover_state(state, quota.resets_at, now)
    active = state.get("active_run")
    measured = None
    if isinstance(active, dict) and active.get("id") == run_id:
        measured = max(0.0, quota.utilization - float(active.get("utilization", quota.utilization)))
        kind = str(active.get("kind", "drain"))
        estimates = state.setdefault("cost_estimates", dict(DEFAULT_COSTS))
        old = float(estimates.get(kind, DEFAULT_COSTS.get(kind, measured)))
        if measured > 0:
            estimates[kind] = round(old * 0.65 + measured * 0.35, 3)
    state["active_run"] = None
    state["last_completed"] = {"at": iso_time(now), "utilization": quota.utilization}
    save_state(path, state)
    return {"measured_cost": measured, "utilization": quota.utilization}


def print_begin(result: dict[str, Any]) -> None:
    mode = "shadow" if result["shadow"] else "enforce"
    print(
        "|".join(
            [
                result["verdict"],
                mode,
                result["would_verdict"],
                result["run_id"],
                result["reason"],
            ]
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--now", help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)
    begin_parser = subparsers.add_parser("begin")
    begin_parser.add_argument("--kind", choices=sorted(DEFAULT_COSTS), required=True)
    complete_parser = subparsers.add_parser("complete")
    complete_parser.add_argument("--run-id", required=True)
    subparsers.add_parser("preflight")
    args = parser.parse_args(argv)
    now = parse_time(args.now) if args.now else utc_now()
    try:
        if args.command == "preflight":
            print(f"preflight|{ensure_claude_token(now)}")
            return 0
        quota = read_live_quota()
        if args.command == "begin":
            print_begin(begin(args.state, args.kind, now, quota))
        else:
            result = complete(args.state, args.run_id, now, quota)
            measured = result["measured_cost"]
            print(f"complete|7d={result['utilization']:.1f}%|measured={measured if measured is not None else 'unknown'}")
        return 0
    except Exception as exc:
        print(f"ERROR|{type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
