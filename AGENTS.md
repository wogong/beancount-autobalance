# Repository Guidelines

## Project Structure & Module Organization
Source lives under `src/`: `auto_balance.py` holds the scheduler logic, `sources.py` wraps RPC fetchers, and `fetch_balance.py` exposes the CLI. Working configuration samples (`config.example.yaml`, optional `.env.example`) are in the same directory; copy them to `config.yaml` when customizing runs, and keep secrets out of version control. Tests reside in `src/tests` and mirror the module layout (`test_auto_balance.py`, etc.). Place new runtime modules inside `src/` and co-locate their tests under `src/tests` using matching file names.

## Build, Test, and Development Commands
Dependencies are managed with `uv`. Run `uv sync` (or `UV_PROJECT_ENVIRONMENT=... uv sync`) after updating requirements. Execute the test suite with `uv run pytest -q src/tests`. When you need to exercise the balance CLI, invoke `uv run python src/fetch_balance.py <token> <chain> <address> --json`. The legacy Makefile exists for compatibility but points at deprecated paths; prefer the `uv` commands above to avoid confusion.

## Coding Style & Naming Conventions
We target modern Python (3.11+) with type hints everywhere they clarify intent. Use four-space indentation, snake_case for functions and variables, and CapWords for classes/dataclasses. Keep modules small and cohesive; helper functions that touch RPCs belong in `sources.py`, while scheduler behavior stays in `auto_balance.py`. Follow black/PEP 8 formatting, maintain import ordering (stdlib, third-party, local), and annotate new public APIs with precise return types.

## Testing Guidelines
Write pytest tests under `src/tests` with filenames starting `test_*.py` and function names mirroring the behavior under test (e.g., `test_process_due_entries_skips_duplicates`). Cover both success paths and failure handling—especially around network fetchers and ledger writes. Run `uv run pytest -q src/tests` before pushing. If a change alters RPC parsing or formatting, add regression tests that exercise representative payloads.

## Commit & Pull Request Guidelines
Commits should use an imperative subject (`Add ledger duplicate guard`) and stay scoped to a single concern. Include a brief body when context or follow-up work matters. For pull requests, provide: (1) a concise summary of the change, (2) testing evidence (command output or reasoning), and (3) any configuration or deployment notes. Link relevant issues and attach CLI output or ledger snippets when they help reviewers validate behavior. Avoid committing secrets from local config files; sanitize examples first.

## Configuration Tips
Store reusable defaults in `config.yaml` (top-level keys should be lowercase). RPC endpoints such as `bsc_endpoint` and `eth_endpoint` are exported to environment variables automatically before fetchers run, but `.env` values can still override them. When testing RPC integrations, supply `--endpoint` to avoid depending on shared keys, and mock network calls in unit tests to keep the suite deterministic.
