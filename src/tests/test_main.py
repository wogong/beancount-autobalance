import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import main


@pytest.mark.asyncio
async def test_healthcheck_notifier_success_ping(monkeypatch):
    notifier = main.HealthcheckNotifier("https://hc-ping.com/example/beancount")
    called = []

    async def fake_ping(url: str) -> None:
        called.append(url)

    monkeypatch.setattr(notifier, "_ping", fake_ping)

    await notifier.notify_success()

    assert called == ["https://hc-ping.com/example/beancount"]


@pytest.mark.asyncio
async def test_healthcheck_notifier_failure_uses_fail_suffix(monkeypatch):
    notifier = main.HealthcheckNotifier("https://hc-ping.com/example/beancount/")
    called = []

    async def fake_ping(url: str) -> None:
        called.append(url)

    monkeypatch.setattr(notifier, "_ping", fake_ping)

    await notifier.notify_failure()

    assert called == ["https://hc-ping.com/example/beancount/fail"]


@pytest.mark.asyncio
async def test_healthcheck_notifier_noop_without_url(monkeypatch):
    notifier = main.HealthcheckNotifier(None)
    called = []

    async def fake_ping(url: str) -> None:
        called.append(url)

    monkeypatch.setattr(notifier, "_ping", fake_ping)

    await notifier.notify_success()
    await notifier.notify_failure()

    assert called == []
