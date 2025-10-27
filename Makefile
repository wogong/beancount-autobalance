.DEFAULT_GOAL := help
SHELL := /bin/bash

PYTHON ?= python3
UV ?= uv

.PHONY: help install run test fetch-balance

help: ## Display this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: ## Install project dependencies with uv
	$(UV) sync

run: ## Execute the daily auto-balance script
	$(PYTHON) src/main.py $(ARGS)

test: ## Run the pytest suite
	$(PYTHON) -m pytest -q src/tests

fetch-balance: ## Fetch a single balance (requires token, chain, address variables)
	@if [ -z "$(token)" ] || [ -z "$(chain)" ] || [ -z "$(address)" ]; then \
		echo "Usage: make fetch-balance token=BNB chain=BSC address=0x... [ARGS=--json]"; \
		exit 1; \
	fi
	$(PYTHON) src/fetch_balance.py $(token) $(chain) $(address) $(ARGS)
