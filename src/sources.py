"""Helper fetchers for auto_balance API integrations."""
from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any, Callable, Optional
from urllib import request

# chain -> (endpoint env var, default Infura URL template keyed by {api_key})
_CHAINS = {
    "bsc": ("BSC_ENDPOINT", "https://bsc-mainnet.infura.io/v3/{api_key}"),
    "ethereum": ("ETH_ENDPOINT", "https://mainnet.infura.io/v3/{api_key}"),
    "base": ("BASE_ENDPOINT", "https://base-mainnet.infura.io/v3/{api_key}"),
}

# Short chain names accepted in config -> canonical _CHAINS key.
_CHAIN_ALIASES = {"eth": "ethereum"}

# (TOKEN, chain) -> (contract address, decimals); contract None means the chain's native coin.
# To support a new token on a chain, add one row here.
_TOKENS = {
    ("BNB", "bsc"): (None, 18),
    ("USDT", "bsc"): ("0x55d398326f99059fF775485246999027B3197955", 18),
    ("USDC", "bsc"): ("0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d", 18),
    ("ETH", "ethereum"): (None, 18),
    ("USDT", "ethereum"): ("0xdAC17F958D2ee523a2206206994597C13D831ec7", 6),
    ("USDC", "ethereum"): ("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eb48", 6),
    ("ETH", "base"): (None, 18),
    ("USDC", "base"): ("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", 6),
}

# ERC-20 balanceOf(address) selector.
_BALANCE_OF_SELECTOR = "0x70a08231"


def fetch_wallet_balance(address: str, api_key: str | None = None, value: str | None = None) -> Decimal:
    """Simple example fetcher that just echoes the provided value."""
    if value is not None:
        return Decimal(value)
    return Decimal("0")


def _fetch_evm_balance(
    chain: str,
    address: str,
    *,
    rpc_method: str,
    decimals: int,
    params: Optional[list] = None,
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None,
    timeout: int = 10,
    opener: Optional[Callable[..., Any]] = None,
) -> Decimal:
    """Query an EVM JSON-RPC endpoint and return a token amount scaled by ``decimals``."""
    if not address:
        raise ValueError("address is required")

    env_var, default_url = _CHAINS[chain]
    url = endpoint or os.getenv(env_var)
    if not url:
        if not api_key:
            raise ValueError(f"Provide {env_var} env, endpoint, or api_key")
        url = default_url.format(api_key=api_key)

    payload = {
        "jsonrpc": "2.0",
        "method": rpc_method,
        "params": params or [address, "latest"],
        "id": 1,
    }

    opener_fn = opener or request.urlopen
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "beancount-autobalance/1.0"},
    )
    with opener_fn(req, timeout=timeout) as response:
        raw = response.read()

    data = json.loads(raw.decode("utf-8"))
    if "error" in data:
        raise ValueError(f"RPC error: {data['error']}")

    result = data.get("result")
    if not isinstance(result, str):
        raise ValueError("Missing balance result in RPC response")

    return Decimal(int(result, 16)) / Decimal(f"1e{decimals}")


def _fetch_erc20_balance(chain: str, contract: str, decimals: int, address: str, **kwargs: Any) -> Decimal:
    if not contract:
        raise ValueError("contract address is required")
    padded_addr = address.lower().replace("0x", "").rjust(64, "0")
    return _fetch_evm_balance(
        chain,
        contract,
        rpc_method="eth_call",
        decimals=decimals,
        params=[{"to": contract, "data": _BALANCE_OF_SELECTOR + padded_addr}, "latest"],
        **kwargs,
    )


def fetch_token_balance(token: str, chain: str, address: str, **kwargs: Any) -> Decimal:
    """Fetch any known (token, chain) balance, resolving contract + decimals from ``_TOKENS``."""
    token = token.upper()
    chain = _CHAIN_ALIASES.get(chain.lower(), chain.lower())
    try:
        contract, decimals = _TOKENS[(token, chain)]
    except KeyError:
        raise ValueError(f"Unknown token {token} on chain {chain}; add it to _TOKENS in sources.py")
    if contract is None:
        return _fetch_evm_balance(chain, address, rpc_method="eth_getBalance", decimals=decimals, **kwargs)
    return _fetch_erc20_balance(chain, contract, decimals, address, **kwargs)


def fetch_bnb_balance_on_bsc(address: str, **kwargs: Any) -> Decimal:
    """Fetch the BNB balance on BSC via an Infura (or compatible) JSON-RPC endpoint."""
    return _fetch_evm_balance("bsc", address, rpc_method="eth_getBalance", decimals=18, **kwargs)


def fetch_eth_balance_on_ethereum(address: str, **kwargs: Any) -> Decimal:
    """Fetch the ETH balance on Ethereum via a JSON-RPC endpoint."""
    return _fetch_evm_balance("ethereum", address, rpc_method="eth_getBalance", decimals=18, **kwargs)


def fetch_erc20_balance_on_bsc(address: str, contract: str, decimals: int, **kwargs: Any) -> Decimal:
    return _fetch_erc20_balance("bsc", contract, decimals, address, **kwargs)


def fetch_erc20_balance_on_ethereum(address: str, contract: str, decimals: int, **kwargs: Any) -> Decimal:
    return _fetch_erc20_balance("ethereum", contract, decimals, address, **kwargs)


def fetch_usdt_balance_on_bsc(**kwargs: Any) -> Decimal:
    return fetch_erc20_balance_on_bsc(contract="0x55d398326f99059fF775485246999027B3197955", decimals=18, **kwargs)


def fetch_usdc_balance_on_bsc(**kwargs: Any) -> Decimal:
    return fetch_erc20_balance_on_bsc(contract="0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d", decimals=18, **kwargs)


def fetch_usdt_balance_on_ethereum(**kwargs: Any) -> Decimal:
    return fetch_erc20_balance_on_ethereum(contract="0xdAC17F958D2ee523a2206206994597C13D831ec7", decimals=6, **kwargs)


def fetch_usdc_balance_on_ethereum(**kwargs: Any) -> Decimal:
    return fetch_erc20_balance_on_ethereum(contract="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eb48", decimals=6, **kwargs)
