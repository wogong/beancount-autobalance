#!/usr/bin/env python3
"""Entry point for generating ledger balance assertions based on config.yaml."""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
import os
from typing import Any, Dict, Iterable

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

    auto_config = load_auto_balance_config(config_data, default_currency=default_currency)
    if not auto_config.entries:
        print("No auto-balance entries configured; nothing to do.")
        return 0

    auto_config.ledger = str(output_path)
    manager = AutoBalanceManager(
        config=auto_config,
        ledger_path=output_path,
        fetcher_registry=default_fetcher_registry(),
    )

    tz = auto_config.timezone
    current_time = datetime.now(tz) if tz else datetime.now()
    additions, errors = await manager.process_due_entries(now=current_time)

    for account, exc in errors:
        account_id = f"{account.account} ({account.currency})"
        print(f"[error] Failed fetching {account_id}: {exc}", file=sys.stderr)

    if additions:
        print(f"Wrote {len(additions)} balance assertion(s) to {output_path}")
    else:
        print("No balance assertions written for today's date.")

    return 0 if not errors else 1


def main() -> None:
    exit_code = asyncio.run(run_once())
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
