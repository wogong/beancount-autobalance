# Beancount AutoBalance

This project automates appending Beancount balance assertions based on a YAML configuration. It reads account entries, optionally resolves live balances through RPC helpers, and writes the results into a ledger-safe output file.

## Repository Layout

- `src/auto_balance.py` – dataclasses and orchestration logic for balance scheduling.
- `src/main.py` – CLI entrypoint that checks today’s date and writes balance assertions.
- `src/sources.py` – RPC helpers for BSC/Ethereum token balances; extend here for new integrations.
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
3. Populate RPC endpoints in the config (e.g., `bsc_endpoint`, `eth_endpoint`). They are automatically exported to environment variables for the balance fetchers, but `.env` values can still override them if present.

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
