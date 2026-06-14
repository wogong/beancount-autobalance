# Beancount AutoBalance

This project automates appending Beancount balance assertions based on a YAML configuration. It reads account entries, optionally resolves live balances through RPC helpers, and writes the results into a ledger-safe output file.

## Repository Layout

- `src/auto_balance.py` – dataclasses and orchestration logic for balance scheduling.
- `src/main.py` – CLI entrypoint that checks today’s date and writes balance assertions.
- `src/sources.py` – EVM JSON-RPC helpers and the `_TOKENS` registry (token + chain → contract/decimals); extend here for new integrations.
- `src/fetch_balance.py` – quick CLI to query individual balances using the helpers above.
- `src/config.yaml` – active configuration (copy from `src/config.example.yaml` to get started).
- `src/tests/` – pytest suite covering the scheduler, loaders, and fetchers.

## Prerequisites

- Python 3.11 or newer.
- Optional but recommended: [`uv`](https://github.com/astral-sh/uv) for environment and dependency management.

Install dependencies with `uv`:

```bash
uv sync
```

If you prefer `pip`, create a virtual environment and install the small dependency set:

```bash
python -m venv .venv
. .venv/bin/activate
pip install pyyaml python-dotenv
```

## Configuration

1. Copy `src/config.example.yaml` to `src/config.yaml`.
2. Adjust the lowercase top-level settings (`default_currency`, `beancount_output`, `bsc_endpoint`, etc.) and the `entries` list to match your ledger.
3. Populate RPC endpoints in the config (e.g., `bsc_endpoint`, `eth_endpoint`, `polygon_endpoint`, `base_endpoint`). Each `<name>_endpoint` key is automatically exported to the `<NAME>_ENDPOINT` environment variable for the balance fetchers, but `.env` values can still override them if present. Keyless public nodes (e.g. `https://bsc-rpc.publicnode.com`) work without an API key; Infura-style URLs need a project id with access to that network.

### Entry types

Each item under `entries` matches one or more days (`date: 15`, or `dates: [7, 14, 21, 28]`, or ISO dates like `2024-07-15`) and produces balance assertions. An account can be either:

- **Static / single fetcher** – list it under `accounts:`. Without an `api_function` the literal `balance` is written; with one (e.g. `sources.fetch_token_balance`) the value is fetched live. Accounts default to `default_currency`, so only non-default ones need `currency`.
- **Crypto shorthand** – a `crypto:` block that expands into one live-fetched account per *(wallet, chain, token)*. Each wallet carries its own `address` and `holdings`; adding a holding is one word in a list:

  ```yaml
  - dates: [7, 14, 21, 28]
    crypto:
      # prefix: Assets:Investments:Crypto:Wallet   # optional; default shown
      chains:            # chain key -> account-name segment (defaults to UPPERCASE)
        eth: Ethereum
        polygon: Polygon
      wallets:
        MAIN:
          address: "0x..."
          holdings:
            bsc: [BNB, USDT, USDC]
            eth: [ETH, USDT, USDC]
            polygon: [POL, USDC]
  ```

  This generates accounts named `<prefix>:<LABEL>:<CHAIN-SEGMENT>:<TOKEN>`, e.g. `Assets:Investments:Crypto:Wallet:MAIN:Ethereum:USDT`.

### Supported chains and tokens

Token resolution lives in the `_TOKENS` registry in `src/sources.py`, keyed by `(TOKEN, chain)` → `(contract, decimals)` (a `None` contract means the chain's native coin). Currently included:

| Chain | Native | Tokens |
| --- | --- | --- |
| `bsc` | BNB | USDT, USDC |
| `eth` / `ethereum` | ETH | USDT, USDC |
| `polygon` | POL | ETH (bridged WETH), USDT, USDC (native, not USDC.e) |
| `base` | ETH | USDT, USDC |

To add a token on a chain, add one row to `_TOKENS`. To add a whole chain, also add an entry to `_CHAINS` (its endpoint env var and a default URL template).

### Idempotency

Re-running on the same day is safe: an account already asserted for that date is skipped. In addition, if a freshly fetched balance equals the account's **most recent** assertion (same value and currency), no new line is appended — so an unchanged balance won't accumulate duplicate assertions across dates.

## Usage

Run `main.py` from the repo root (it automatically locates `src/`):

```bash
python src/main.py --config src/config.yaml --output ./beancount_output.beancount
```

This command appends balance assertions for entries whose configured day matches today.

To inspect a single balance via the helper CLI run:

```bash
python src/fetch_balance.py BNB BSC 0xYourWallet --json --config src/config.yaml
```

## Testing

Execute the test suite with:

```bash
pytest -q src/tests
```

All new source or fetcher additions should come with matching tests under `src/tests/`.
