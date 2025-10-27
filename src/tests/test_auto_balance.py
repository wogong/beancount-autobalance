import asyncio
import json
import os
import sys
import textwrap
from argparse import Namespace
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from auto_balance import (
    AutoBalanceManager,
    default_fetcher_registry,
    load_auto_balance_config,
    parse_date_matchers,
)
from sources import (
    fetch_bnb_balance_on_bsc,
    fetch_eth_balance_on_ethereum,
    fetch_usdc_balance_on_bsc,
    fetch_usdc_balance_on_ethereum,
    fetch_usdt_balance_on_bsc,
    fetch_usdt_balance_on_ethereum,
)
import main


def test_parse_date_matchers_supports_day_and_iso():
    from datetime import date

    matchers = parse_date_matchers(["5", "2024-07-15"])
    assert any(m.day_of_month == 5 for m in matchers)
    assert any(m.exact_date == date(2024, 7, 15) for m in matchers)


def test_auto_balance_config_defaults_runtime():
    config_data = {
        'auto_balance': {
            'entries': [
                {
                    'date': 5,
                    'accounts': [{'account': 'Assets:Cash', 'currency': 'USD', 'balance': '0'}],
                }
            ]
        }
    }
    config = load_auto_balance_config(config_data, 'USD')
    assert config.runtime == time(1, 0)


def test_auto_balance_config_uses_runtime_from_config():
    config_data = {
        'auto_balance': {
            'runtime': '05:45',
            'entries': [
                {
                    'date': 5,
                    'accounts': [{'account': 'Assets:Cash', 'currency': 'USD', 'balance': '0'}],
                }
            ]
        }
    }
    config = load_auto_balance_config(config_data, 'USD')
    assert config.runtime == time(5, 45)


def test_auto_balance_manager_appends_balance(tmp_path):
    config_data = {
        'auto_balance': {
            'entries': [
                {
                    'date': 15,
                    'accounts': [
                        {'account': 'Assets:Cash', 'currency': 'USD', 'balance': '0'},
                    ],
                }
            ]
        }
    }
    config = load_auto_balance_config(config_data, 'USD')
    ledger_path = tmp_path / 'auto.beancount'
    manager = AutoBalanceManager(config=config, ledger_path=ledger_path, fetcher_registry=default_fetcher_registry())

    now = datetime(2024, 7, 15, 3, 0, 0)
    additions, errors = asyncio.run(manager.process_due_entries(now=now))

    assert errors == []
    assert len(additions) == 1
    assert ledger_path.read_text(encoding='utf-8').startswith('2024-07-15 balance Assets:Cash 0.00 USD')

    second_run, _ = asyncio.run(manager.process_due_entries(now=now))
    assert second_run == []


def test_auto_balance_manager_uses_api_function(tmp_path):
    def dummy_fetcher(value):
        return value

    config_data = {
        'auto_balance': {
            'entries': [
                {
                    'date': '01',
                    'accounts': [
                        {
                            'account': 'Assets:Crypto:Wallet',
                            'currency': 'BTC',
                            'api_function': 'dummy',
                            'args': {'value': '0.12345678'},
                            'precision': 8,
                        }
                    ],
                }
            ]
        }
    }

    config = load_auto_balance_config(config_data, 'USD')
    ledger_path = tmp_path / 'crypto.beancount'
    manager = AutoBalanceManager(config=config, ledger_path=ledger_path, fetcher_registry={'dummy': dummy_fetcher})

    now = datetime(2024, 7, 1, 0, 0, 0)
    additions, errors = asyncio.run(manager.process_due_entries(now=now))

    assert errors == []
    assert len(additions) == 1
    assert '0.12345678 BTC' in ledger_path.read_text(encoding='utf-8')


def test_fetch_bnb_balance_on_bsc_parses_rpc_response():
    class DummyResponse:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode('utf-8')

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def open_stub(req, timeout):
        body = json.loads(req.data.decode('utf-8'))
        assert body['method'] == 'eth_getBalance'
        assert body['params'][0] == '0x0000000000000000000000000000000000000000'
        return DummyResponse({'jsonrpc': '2.0', 'id': 1, 'result': hex(10**18)})

    balance = fetch_bnb_balance_on_bsc(
        address='0x0000000000000000000000000000000000000000',
        api_key='key',
        opener=open_stub,
    )
    assert balance == Decimal('1')


def _dummy_rpc_response(hex_value):
    class DummyResponse:
        def __init__(self, result_hex):
            self.result_hex = result_hex

        def read(self):
            return json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': self.result_hex}).encode('utf-8')

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    return DummyResponse(hex_value)


def test_fetch_usdt_balance_on_bsc_uses_token_contract():
    captured = {}

    def open_stub(req, timeout):
        body = json.loads(req.data.decode('utf-8'))
        captured['body'] = body
        return _dummy_rpc_response(hex(1230000000000000000))

    balance = fetch_usdt_balance_on_bsc(
        address='0xb794f5ea0ba39494ce839613fffba74279579268',
        api_key='key',
        opener=open_stub,
    )

    params = captured['body']['params']
    assert captured['body']['method'] == 'eth_call'
    assert params[0]['to'].lower() == '0x55d398326f99059ff775485246999027b3197955'
    assert params[0]['data'].startswith('0x70a08231')
    assert balance == Decimal('1.23')


def test_fetch_usdc_balance_on_bsc_respects_decimals():
    captured = {}

    def open_stub(req, timeout):
        body = json.loads(req.data.decode('utf-8'))
        captured['body'] = body
        return _dummy_rpc_response(hex(5 * 10**17))

    balance = fetch_usdc_balance_on_bsc(
        address='0xb794f5ea0ba39494ce839613fffba74279579268',
        api_key='key',
        opener=open_stub,
    )

    assert captured['body']['method'] == 'eth_call'
    assert captured['body']['params'][0]['to'].lower() == '0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d'
    assert balance == Decimal('0.5')


def test_fetch_eth_balance_on_ethereum_parses_rpc_response():
    class DummyResponse:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode('utf-8')

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def open_stub(req, timeout):
        body = json.loads(req.data.decode('utf-8'))
        assert body['method'] == 'eth_getBalance'
        assert body['params'][0] == '0xb794f5ea0ba39494ce839613fffba74279579268'
        return DummyResponse({'jsonrpc': '2.0', 'id': 1, 'result': hex(2 * 10**18)})

    balance = fetch_eth_balance_on_ethereum(
        address='0xb794f5ea0ba39494ce839613fffba74279579268',
        api_key='key',
        opener=open_stub,
    )
    assert balance == Decimal('2')


def test_fetch_usdt_balance_on_ethereum_uses_token_contract():
    captured = {}

    def open_stub(req, timeout):
        body = json.loads(req.data.decode('utf-8'))
        captured['body'] = body
        return _dummy_rpc_response(hex(1_230_000))

    balance = fetch_usdt_balance_on_ethereum(
        address='0xb794f5ea0ba39494ce839613fffba74279579268',
        api_key='key',
        opener=open_stub,
    )

    params = captured['body']['params']
    assert captured['body']['method'] == 'eth_call'
    assert params[0]['to'].lower() == '0xdac17f958d2ee523a2206206994597c13d831ec7'
    assert params[0]['data'].startswith('0x70a08231')
    assert balance == Decimal('1.23')


def test_fetch_usdc_balance_on_ethereum_respects_decimals():
    captured = {}

    def open_stub(req, timeout):
        body = json.loads(req.data.decode('utf-8'))
        captured['body'] = body
        return _dummy_rpc_response(hex(500_000))

    balance = fetch_usdc_balance_on_ethereum(
        address='0xb794f5ea0ba39494ce839613fffba74279579268',
        api_key='key',
        opener=open_stub,
    )

    assert captured['body']['method'] == 'eth_call'
    assert captured['body']['params'][0]['to'].lower() == '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
    assert balance == Decimal('0.5')


def test_main_generates_balance_assertion(tmp_path, monkeypatch):
    today = datetime.now().day
    output_path = tmp_path / 'beancount_output.beancount'
    config_path = tmp_path / 'config.yaml'
    endpoint = 'https://example.invalid'
    config_text = textwrap.dedent(
        f"""
        default_currency: usd
        beancount_output: {output_path}
        bsc_endpoint: "{endpoint}"
        entries:
          - date: {today}
            accounts:
              - account: Assets:Cash:Wallet
                currency: USD
        """
    )
    config_path.write_text(config_text, encoding='utf-8')

    args = Namespace(config=config_path, output=output_path)
    monkeypatch.setattr(main, 'parse_args', lambda: args)
    monkeypatch.delenv('BSC_ENDPOINT', raising=False)

    exit_code = asyncio.run(main.run_once())
    assert exit_code == 0
    assert output_path.exists()
    ledger_text = output_path.read_text(encoding='utf-8')
    assert 'balance Assets:Cash:Wallet' in ledger_text
    assert 'USD' in ledger_text
    assert os.getenv('BSC_ENDPOINT') == endpoint
