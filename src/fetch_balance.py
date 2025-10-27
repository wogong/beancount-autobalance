#!/usr/bin/env python3
"""CLI helper to fetch token balances via sources helpers."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable, Dict, Tuple

from dotenv import load_dotenv

import sources
from main import apply_env_overrides, load_config

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


CHAIN_ENDPOINT_ENV = {
    "bsc": "BSC_ENDPOINT",
    "ethereum": "ETH_ENDPOINT",
}


FETCHER_MAP: Dict[Tuple[str, str], Callable[..., object]] = {
    ("bnb", "bsc"): sources.fetch_bnb_balance_on_bsc,
    ("usdt", "bsc"): sources.fetch_usdt_balance_on_bsc,
    ("usdc", "bsc"): sources.fetch_usdc_balance_on_bsc,
    ("eth", "ethereum"): sources.fetch_eth_balance_on_ethereum,
    ("usdt", "ethereum"): sources.fetch_usdt_balance_on_ethereum,
    ("usdc", "ethereum"): sources.fetch_usdc_balance_on_ethereum,
}


def resolve_fetcher(token: str, chain: str) -> Callable[..., object]:
    key = (token.lower(), chain.lower())
    if key in FETCHER_MAP:
        return FETCHER_MAP[key]

    candidate = f"fetch_{token.lower()}_balance_on_{chain.lower()}"
    if hasattr(sources, candidate):
        return getattr(sources, candidate)

    raise SystemExit(f"Unknown balance fetcher for token={token}, chain={chain}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch token balance via configured RPC helpers")
    parser.add_argument("token", help="Token symbol (e.g., BNB, USDT)")
    parser.add_argument("chain", help="Chain identifier (e.g., BSC)")
    parser.add_argument("address", help="Wallet address (0x...) to query")
    parser.add_argument("--api-key", help="API key (Infura project ID, etc.)")
    parser.add_argument("--endpoint", help="Explicit RPC endpoint URL (overrides --api-key)")
    parser.add_argument("--timeout", type=int, default=10, help="Request timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Return machine-readable JSON")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to YAML configuration file with endpoint defaults.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv()
    if args.config and args.config.exists():
        config_data = load_config(args.config)
        apply_env_overrides(config_data)
    fetcher = resolve_fetcher(args.token, args.chain)

    kwargs = {
        "address": args.address,
        "timeout": args.timeout,
    }
    if args.api_key:
        kwargs["api_key"] = args.api_key
    endpoint = args.endpoint
    if not endpoint:
        env_key = CHAIN_ENDPOINT_ENV.get(args.chain.lower(), f"{args.chain.upper()}_ENDPOINT")
        endpoint = os.getenv(env_key)
    if endpoint:
        kwargs["endpoint"] = endpoint

    try:
        balance = fetcher(**kwargs)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"token": args.token, "chain": args.chain, "address": args.address, "balance": str(balance)}))
    else:
        print(f"Token: {args.token}\nChain: {args.chain}\nAddress: {args.address}\nBalance: {balance}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
