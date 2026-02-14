#!/usr/bin/env python3
"""Entry point for generating ledger balance assertions based on config.yaml."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable

import urllib.request

import yaml

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from auto_balance import AutoBalanceManager, default_fetcher_registry, load_auto_balance_config  # noqa: E402

ENV_KEY_SUFFIXES: Iterable[str] = (
    "_endpoint",
    "_api_key",
    "_token",
)

HEALTHCHECK_TIMEOUT_SECONDS = 10
HEALTHCHECK_USER_AGENT = "beancount-autobalance/1.0"


class HealthcheckNotifier:
    """Send success/failure notifications to a configured healthcheck endpoint."""

    def __init__(self, base_url: Any) -> None:
        url = str(base_url).strip() if base_url else ""
        self.success_url: str | None = url or None
        self.failure_url: str | None = None
        if self.success_url:
            stripped = self.success_url.rstrip("/")
            self.failure_url = f"{stripped}/fail"

    async def notify_success(self) -> None:
        if self.success_url:
            await self._ping(self.success_url)

    async def notify_failure(self) -> None:
        url = self.failure_url or self.success_url
        if url:
            await self._ping(url)

    async def _ping(self, url: str) -> None:
        try:
            await asyncio.to_thread(self._ping_sync, url)
        except RuntimeError:
            self._ping_sync(url)

    @staticmethod
    def _ping_sync(url: str) -> None:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": HEALTHCHECK_USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=HEALTHCHECK_TIMEOUT_SECONDS) as response:
                # Read a small amount to force the request to complete.
                response.read(1)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] Healthcheck ping failed for {url}: {exc}", file=sys.stderr)


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date value '{value}'; expected YYYY-MM-DD.") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate balance assertions for matching config entries.")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT_DIR / "config.yaml",
        help="Path to YAML configuration file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override beancount output file path.",
    )
    parser.add_argument(
        "--date",
        dest="dates",
        action="extend",
        type=parse_iso_date,
        nargs="+",
        help="ISO date(s) (YYYY-MM-DD) to process; may be provided multiple times.",
    )
    return parser.parse_args()


def load_config(config_path: Path) -> Dict[str, Any]:
    try:
        raw = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"Config file not found: {config_path}") from exc

    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise SystemExit("Config file must define a mapping at the top level.")
    return {str(key).lower(): value for key, value in data.items()}


def apply_env_overrides(config: Dict[str, Any]) -> None:
    for key, value in config.items():
        if not isinstance(value, str):
            continue
        key_lower = key.lower()
        if any(key_lower.endswith(suffix) for suffix in ENV_KEY_SUFFIXES):
            os.environ[key_lower.upper()] = value


def resolve_output_path(config: Dict[str, Any], override: Path | None) -> Path:
    if override:
        return override.resolve()
    candidates = [
        config.get("beancount_output"),
        config.get("ledger"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            path = Path(candidate)
            if not path.is_absolute():
                path = (ROOT_DIR / path).resolve()
            return path
    return (ROOT_DIR / "beancount_output").resolve()


async def run_once() -> int:
    args = parse_args()
    config_data = load_config(args.config)
    apply_env_overrides(config_data)
    output_path = resolve_output_path(config_data, args.output)
    default_currency = str(config_data.get("default_currency", "USD")).upper()
    healthcheck = HealthcheckNotifier(config_data.get("healthcheck_url"))

    auto_config = load_auto_balance_config(config_data, default_currency=default_currency)
    if not auto_config.entries:
        print("No auto-balance entries configured; nothing to do.")
        await healthcheck.notify_success()
        return 0

    auto_config.ledger = str(output_path)
    manager = AutoBalanceManager(
        config=auto_config,
        ledger_path=output_path,
        fetcher_registry=default_fetcher_registry(),
    )

    tz = auto_config.timezone
    current_time = datetime.now(tz) if tz else datetime.now()
    requested_dates = getattr(args, "dates", None) or []
    try:
        if requested_dates:
            additions, errors = await manager.process_due_entries(target_dates=requested_dates)
        else:
            additions, errors = await manager.process_due_entries(now=current_time)
    except Exception:
        await healthcheck.notify_failure()
        raise

    for account, exc in errors:
        account_id = f"{account.account} ({account.currency})"
        print(f"[error] Failed fetching {account_id}: {exc}", file=sys.stderr)

    if additions:
        print(f"Wrote {len(additions)} balance assertion(s) to {output_path}")
    else:
        scope_text = "the requested date(s)" if requested_dates else "today's date"
        print(f"No balance assertions written for {scope_text}.")

    exit_code = 0 if not errors else 1
    if exit_code == 0:
        await healthcheck.notify_success()
    else:
        await healthcheck.notify_failure()
    return exit_code


def main() -> None:
    exit_code = asyncio.run(run_once())
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
