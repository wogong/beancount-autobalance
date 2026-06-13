"""Auto-balance helpers for scheduling ledger balance assertions."""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from zoneinfo import ZoneInfo

DEFAULT_PRECISION = 2


@dataclass(frozen=True)
class DateMatcher:
    """Represents either a specific calendar date or a monthly day."""

    day_of_month: Optional[int] = None
    exact_date: Optional[date] = None

    def matches(self, today: date) -> bool:
        if self.exact_date:
            return today == self.exact_date
        if self.day_of_month is None:
            return False
        return today.day == self.day_of_month


@dataclass
class AutoBalanceAccount:
    account: str
    currency: str
    balance: Decimal = Decimal("0")
    api_function: Optional[str] = None
    args: Dict[str, Any] = field(default_factory=dict)
    precision: int = DEFAULT_PRECISION

    async def resolve_amount(self, fetcher_registry: Dict[str, Callable[..., Any]]) -> Decimal:
        if not self.api_function:
            return self.balance

        fetcher = resolve_fetcher(self.api_function, fetcher_registry)
        result = fetcher(**self.args)
        if inspect.isawaitable(result):
            result = await result  # type: ignore[assignment]
        return coerce_decimal(result)

    def format_amount(self, amount: Decimal) -> str:
        scale = Decimal("1").scaleb(-self.precision)
        quantized = amount.quantize(scale)
        return format(quantized, "f")


@dataclass
class AutoBalanceEntry:
    dates: Sequence[DateMatcher]
    accounts: Sequence[AutoBalanceAccount]
    description: Optional[str] = None

    def is_due(self, today: date) -> bool:
        return any(matcher.matches(today) for matcher in self.dates)


@dataclass
class AutoBalanceConfig:
    entries: Sequence[AutoBalanceEntry]
    timezone: Optional[ZoneInfo] = None


@dataclass
class AutoBalanceResult:
    account: AutoBalanceAccount
    amount: Decimal
    line: str


@dataclass
class AutoBalanceManager:
    config: AutoBalanceConfig
    ledger_path: Path
    fetcher_registry: Dict[str, Callable[..., Any]]

    def __post_init__(self) -> None:
        self._processed: set[Tuple[str, str]] = set()

    async def process_due_entries(
        self,
        now: Optional[datetime] = None,
        target_dates: Optional[Sequence[date]] = None,
    ) -> Tuple[List[AutoBalanceResult], List[Tuple[AutoBalanceAccount, Exception]]]:
        if not self.config.entries:
            return [], []

        dates_to_process: List[date] = []
        if target_dates:
            for candidate in target_dates:
                if isinstance(candidate, datetime):
                    dates_to_process.append(candidate.date())
                elif isinstance(candidate, date):
                    dates_to_process.append(candidate)
                else:
                    raise TypeError(f"Unsupported target date type: {type(candidate)!r}")
        else:
            if now is None:
                tz = self.config.timezone
                now = datetime.now(tz) if tz else datetime.now()
            dates_to_process.append(now.date())

        if not dates_to_process:
            return [], []

        seen: Dict[str, None] = {}
        ordered_dates: List[date] = []
        for item in dates_to_process:
            key = item.isoformat()
            if key not in seen:
                seen[key] = None
                ordered_dates.append(item)

        additions: List[AutoBalanceResult] = []
        errors: List[Tuple[AutoBalanceAccount, Exception]] = []

        for target_date in ordered_dates:
            for entry in self.config.entries:
                if not entry.is_due(target_date):
                    continue
                for account in entry.accounts:
                    key = (account.account, target_date.isoformat())
                    if key in self._processed:
                        continue
                    if self._has_existing_line(target_date, account.account):
                        self._processed.add(key)
                        continue
                    try:
                        amount = await account.resolve_amount(self.fetcher_registry)
                    except Exception as exc:  # pragma: no cover
                        errors.append((account, exc))
                        continue

                    line = format_balance_line(target_date, account, amount)
                    try:
                        append_balance_line(self.ledger_path, line)
                    except Exception as exc:  # pragma: no cover
                        errors.append((account, exc))
                        continue

                    self._processed.add(key)
                    additions.append(AutoBalanceResult(account=account, amount=amount, line=line))

        return additions, errors

    def _has_existing_line(self, target_date: date, account_name: str) -> bool:
        prefix = f"{target_date.isoformat()} balance {account_name}"
        if not self.ledger_path.exists():
            return False

        try:
            with self.ledger_path.open("r", encoding="utf-8") as ledger:
                for raw_line in ledger:
                    if raw_line.strip().startswith(prefix):
                        return True
        except FileNotFoundError:
            return False
        return False


def append_balance_line(ledger_path: Path, line: str) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as ledger:
        ledger.write(line)
        if not line.endswith("\n"):
            ledger.write("\n")


def format_balance_line(entry_date: date, account: AutoBalanceAccount, amount: Decimal) -> str:
    amount_text = account.format_amount(amount)
    return f"{entry_date.isoformat()} balance {account.account} {amount_text} {account.currency}\n"


def coerce_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise ValueError(f"Unsupported balance value type: {type(value)!r}")


def resolve_fetcher(name: str, registry: Dict[str, Callable[..., Any]]) -> Callable[..., Any]:
    if name in registry:
        return registry[name]
    if "." in name:
        module_name, func_name = name.rsplit(".", 1)
        module = import_module(module_name)
        return getattr(module, func_name)
    raise KeyError(f"Unknown balance fetcher '{name}'")


def parse_date_matchers(raw_date: Any) -> List[DateMatcher]:
    matchers: List[DateMatcher] = []
    if raw_date is None:
        return matchers

    if isinstance(raw_date, list):
        for item in raw_date:
            matchers.extend(parse_date_matchers(item))
        return matchers

    if isinstance(raw_date, int):
        if 1 <= raw_date <= 31:
            matchers.append(DateMatcher(day_of_month=raw_date))
        return matchers

    if isinstance(raw_date, str):
        stripped = raw_date.strip()
        if stripped.isdigit():
            value = int(stripped)
            if 1 <= value <= 31:
                matchers.append(DateMatcher(day_of_month=value))
                return matchers
        try:
            exact = date.fromisoformat(stripped)
            matchers.append(DateMatcher(exact_date=exact))
        except ValueError:
            pass
        return matchers

    return matchers


def parse_account(entry: Dict[str, Any], default_currency: str) -> Optional[AutoBalanceAccount]:
    account_name = entry.get("account")
    if not account_name:
        return None
    currency_value = entry.get("currency") or default_currency
    currency = str(currency_value).strip().upper()
    precision = entry.get("precision", DEFAULT_PRECISION)
    try:
        precision_value = int(precision)
        if precision_value < 0:
            precision_value = DEFAULT_PRECISION
    except (TypeError, ValueError):
        precision_value = DEFAULT_PRECISION

    balance_value = entry.get("balance")
    balance = coerce_decimal(balance_value) if balance_value is not None else Decimal("0")

    api_function = entry.get("api_function")
    args = entry.get("args") or {}
    if not isinstance(args, dict):
        args = {}

    return AutoBalanceAccount(
        account=account_name,
        currency=str(currency),
        balance=balance,
        api_function=api_function,
        args=args,
        precision=precision_value,
    )


def load_auto_balance_config(config_data: Dict[str, Any], default_currency: str) -> AutoBalanceConfig:
    default_currency = str(default_currency).strip().upper()

    timezone = None
    timezone_name = config_data.get("timezone")
    if timezone_name:
        try:
            timezone = ZoneInfo(timezone_name)
        except Exception:
            timezone = None

    entries: List[AutoBalanceEntry] = []
    for raw_entry in config_data.get("entries") or []:
        if not isinstance(raw_entry, dict):
            continue
        matchers = parse_date_matchers(_entry_date_field(raw_entry))
        if not matchers:
            continue
        accounts_data = raw_entry.get("accounts")
        if isinstance(accounts_data, dict):
            accounts_data = [accounts_data]
        if not isinstance(accounts_data, list):
            accounts_data = []
        crypto = raw_entry.get("crypto")
        if isinstance(crypto, dict):
            accounts_data = list(accounts_data) + _expand_crypto(crypto)
        if not accounts_data:
            continue
        accounts = [
            account
            for account in (
                parse_account(item, default_currency) for item in accounts_data if isinstance(item, dict)
            )
            if account
        ]
        if not accounts:
            continue
        entries.append(
            AutoBalanceEntry(
                dates=matchers,
                accounts=accounts,
                description=raw_entry.get("description"),
            )
        )

    return AutoBalanceConfig(entries=entries, timezone=timezone)


CRYPTO_PREFIX = "Assets:Investments:Crypto:Wallet"
# Ledger display precision per token; native coins keep more decimals than stablecoins.
_CRYPTO_PRECISION = {"BNB": 6, "ETH": 6}
_DEFAULT_CRYPTO_PRECISION = 2


def _expand_crypto(crypto: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Expand a `crypto` shorthand block into per-(wallet, chain, token) account dicts.

    Each wallet carries its own address and holdings:
        crypto:
          prefix: Assets:Investments:Crypto:Wallet   # optional
          wallets:
            LABEL:
              address: 0x...
              holdings: {chain: [TOKEN, ...], ...}
    """
    prefix = str(crypto.get("prefix") or CRYPTO_PREFIX).rstrip(":")
    wallets = crypto.get("wallets") or {}

    accounts: List[Dict[str, Any]] = []
    for label, spec in wallets.items():
        if not isinstance(spec, dict):
            continue
        address = spec.get("address")
        holdings = spec.get("holdings") or {}
        for chain, tokens in holdings.items():
            for token in tokens or []:
                token = str(token).upper()
                accounts.append(
                    {
                        "account": f"{prefix}:{label}:{str(chain).upper()}:{token}",
                        "currency": token,
                        "api_function": "sources.fetch_token_balance",
                        "args": {"token": token, "chain": str(chain), "address": address},
                        "precision": _CRYPTO_PRECISION.get(token, _DEFAULT_CRYPTO_PRECISION),
                    }
                )
    return accounts


def _entry_date_field(raw_entry: Dict[str, Any]) -> Any:
    """Merge the `date` and `dates` keys of an entry into a single value for matching."""
    raw_date = raw_entry.get("date")
    if "dates" not in raw_entry:
        return raw_date
    dates_field = raw_entry.get("dates")
    return dates_field if raw_date is None else [raw_date, dates_field]


def default_fetcher_registry() -> Dict[str, Callable[..., Any]]:
    return {
        "constant": lambda value="0", **_: Decimal(str(value)),
    }
