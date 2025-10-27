.DEFAULT_GOAL := help
SHELL := /bin/bash

PYTHON ?= python3
UV ?= uv
SYSTEMCTL ?= systemctl
JOURNALCTL ?= journalctl
SYSTEMD_DIR ?= $(HOME)/.config/systemd/user
SERVICE_NAME ?= beancount-autobalance
SERVICE_UNIT := $(SERVICE_NAME).service
TIMER_UNIT := $(SERVICE_NAME).timer
CONFIG_PATH ?= $(CURDIR)/src/config.yaml
ON_CALENDAR ?= daily
REPO_PATH := $(CURDIR)
UV_PATH := $(shell command -v $(UV) 2>/dev/null)
ifeq ($(strip $(UV_PATH)),)
UV_BIN := $(UV)
else
UV_BIN := $(UV_PATH)
endif
USER_PATH := $(shell printf '%s' "$$PATH")
LOG_ARGS ?= -f

.PHONY: help install run test fetch-balance service start stop restart status log

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

service: ## Install or update the systemd user service and timer
	@mkdir -p "$(SYSTEMD_DIR)"
	sed -e "s|{{REPO_PATH}}|$(REPO_PATH)|g" \
		-e "s|{{UV_BIN}}|$(UV_BIN)|g" \
		-e "s|{{CONFIG_PATH}}|$(CONFIG_PATH)|g" \
		-e "s|{{PATH}}|$(USER_PATH)|g" \
		systemd/beancount-autobalance.service > "$(SYSTEMD_DIR)/$(SERVICE_UNIT)"
	sed -e "s|{{ON_CALENDAR}}|$(ON_CALENDAR)|g" \
		-e "s|{{SERVICE_UNIT}}|$(SERVICE_UNIT)|g" \
		systemd/beancount-autobalance.timer > "$(SYSTEMD_DIR)/$(TIMER_UNIT)"
	$(SYSTEMCTL) --user daemon-reload
	$(SYSTEMCTL) --user enable --now "$(TIMER_UNIT)"

start: ## Start the auto-balance systemd timer
	$(SYSTEMCTL) --user start "$(TIMER_UNIT)"

stop: ## Stop the auto-balance systemd timer
	$(SYSTEMCTL) --user stop "$(TIMER_UNIT)"

restart: ## Restart the auto-balance systemd timer
	$(SYSTEMCTL) --user restart "$(TIMER_UNIT)"

status: ## Show status for the auto-balance systemd timer
	$(SYSTEMCTL) --user status "$(TIMER_UNIT)"

log: ## Tail journal logs for the auto-balance service
	$(JOURNALCTL) --user-unit "$(SERVICE_UNIT)" $(LOG_ARGS)
