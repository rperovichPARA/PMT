"""Data models and portfolio business logic for Taiyo PMT."""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Layout constants – single source of truth for column indices
# ---------------------------------------------------------------------------

FIXED_COLUMNS = ["", "Symbol", "Name", "Price (JPY)", "% of Company"]
FUND_COLUMNS = ["Curr.", "New"]
NUM_FIXED_COLUMNS = len(FIXED_COLUMNS)
NUM_FUND_COLUMNS = len(FUND_COLUMNS)

CASH_SYMBOLS = frozenset({"JPY", "USD"})

DEFAULT_EXCHANGE_RATE = 100.0

# Fund background colours (R, G, B tuples)
FUND_COLORS_RGB = [
    (230, 242, 255),  # Light blue
    (230, 255, 230),  # Light green
    (255, 242, 230),  # Light orange
    (242, 230, 255),  # Light purple
]

BUY_COLOR_RGB = (150, 255, 150)
SELL_COLOR_RGB = (255, 150, 150)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FundPosition:
    """A single fund's holding of a security."""

    quantity: float = 0.0
    pct_of_company: float = 0.0

    # Computed at display-refresh time
    value_jpy: float = 0.0
    value_usd: float = 0.0
    weight: float = 0.0
    rel_weight: float = 0.0
    new_rel_weight: float = 0.0


@dataclass
class Position:
    """Aggregate position for one security across all funds."""

    symbol: str = ""
    name: str = ""
    price: float = 0.0
    is_cash: bool = False
    adv_10pct: float = 0.0
    currency: str = "JPY"
    os_shares: float = 0.0
    funds: dict[str, FundPosition] = field(default_factory=dict)

    @property
    def total_pct_of_company(self) -> float:
        return sum(fp.pct_of_company for fp in self.funds.values())

    @property
    def total_quantity(self) -> float:
        return sum(fp.quantity for fp in self.funds.values())

    def calculate_pct_of_company(self) -> float:
        """Derive total % of company from share counts when explicit data is missing."""
        if self.os_shares > 0 and self.total_quantity > 0:
            return self.total_quantity / self.os_shares
        return self.total_pct_of_company


@dataclass
class ProposedExecution:
    """One fund-level proposed trade."""

    fund: str = ""
    symbol: str = ""
    trade_type: str = ""  # "Buy" or "Sell"
    trade_quantity: float = 0.0
    target_raw: float = 0.0
    trade_value_usd: float = 0.0
    trade_value_signed: float = 0.0
    trading_days: float = 0.0
    target_price: float | None = None
    pct_to_curr: float | None = None


@dataclass
class FilingRecord:
    """Filing information for a single security."""

    name: str = ""
    date: str | None = None
    last_filing: float | None = None


# ---------------------------------------------------------------------------
# Portfolio helper functions (pure logic, no UI)
# ---------------------------------------------------------------------------

def calculate_value_usd(value_jpy: float, usd_jpy_rate: float) -> float:
    """Convert JPY to USD using the exchange rate."""
    rate = usd_jpy_rate if usd_jpy_rate > 1.0 else DEFAULT_EXCHANGE_RATE
    return value_jpy / rate


def fund_column_index(fund_idx: int, sub_col: int) -> int:
    """Return the absolute table-column for a fund's sub-column (0=Curr, 1=New)."""
    return NUM_FIXED_COLUMNS + fund_idx * NUM_FUND_COLUMNS + sub_col


def calculate_trade_from_raw(
    portfolio: dict[str, Position],
    fund_name: str,
    symbol: str,
    new_raw: float,
    usd_jpy_rate: float,
) -> dict | None:
    """Compute trade details when the user changes the target RAW.

    Returns a dict with keys: trade_type, trade_quantity, trade_value_jpy,
    trade_value_usd or ``None`` on invalid input.
    """
    if symbol not in portfolio:
        return None
    position = portfolio[symbol]
    price = position.price
    if price <= 0:
        return None

    securities_count = 0
    total_portfolio_jpy = 0.0

    for pos in portfolio.values():
        if pos.is_cash:
            continue
        if fund_name in pos.funds and pos.funds[fund_name].quantity > 0:
            securities_count += 1
            total_portfolio_jpy += pos.price * pos.funds[fund_name].quantity

    if securities_count == 0 or total_portfolio_jpy <= 0:
        return None

    fund_pos = position.funds.get(fund_name)
    current_qty = fund_pos.quantity if fund_pos else 0
    current_position_jpy = price * current_qty

    avg_weight = 100.0 / securities_count
    target_weight = new_raw * avg_weight
    target_position_jpy = (target_weight / 100.0) * total_portfolio_jpy
    trade_value_jpy = target_position_jpy - current_position_jpy

    trade_type = "Buy" if trade_value_jpy > 0 else "Sell"
    trade_quantity = round(abs(trade_value_jpy / price))
    if trade_type == "Sell":
        trade_quantity = -trade_quantity

    rate = usd_jpy_rate if usd_jpy_rate > 0 else DEFAULT_EXCHANGE_RATE
    trade_value_usd = trade_value_jpy / rate

    return {
        "trade_type": trade_type,
        "trade_quantity": trade_quantity,
        "trade_value_jpy": trade_value_jpy,
        "trade_value_usd": trade_value_usd,
    }


def calculate_target_raw_from_shares(
    portfolio: dict[str, Position],
    fund_name: str,
    symbol: str,
    current_quantity: float,
    trade_shares: float,
    side: str,
) -> float | None:
    """Reverse-calculate the target RAW from a share-count trade."""
    if symbol not in portfolio:
        return None
    position = portfolio[symbol]
    price = position.price
    if price <= 0:
        return None

    securities_count = 0
    total_portfolio_jpy = 0.0

    for pos in portfolio.values():
        if pos.is_cash:
            continue
        if fund_name in pos.funds and pos.funds[fund_name].quantity > 0:
            securities_count += 1
            total_portfolio_jpy += pos.price * pos.funds[fund_name].quantity

    if securities_count == 0 or total_portfolio_jpy <= 0:
        return None

    current_position_jpy = price * current_quantity

    trade_value_jpy = price * abs(trade_shares)
    if side.startswith("Sell"):
        trade_value_jpy = -trade_value_jpy

    new_position_jpy = current_position_jpy + trade_value_jpy
    new_portfolio_jpy = total_portfolio_jpy + trade_value_jpy

    if new_portfolio_jpy <= 0:
        return None
    new_weight = (new_position_jpy / new_portfolio_jpy) * 100.0
    avg_weight = 100.0 / securities_count
    if avg_weight <= 0:
        return None
    return new_weight / avg_weight


def normalize_symbol(ticker: str) -> str:
    """Normalize an imported ticker to the canonical portfolio symbol."""
    if ticker is None:
        return ""
    import pandas as pd

    if isinstance(ticker, float) and pd.isna(ticker):
        return ""

    ticker = str(ticker).strip()
    if not ticker:
        return ""

    if " JP" in ticker:
        return ticker.split(" JP")[0].strip()

    if ticker.isdigit():
        return ticker
    if len(ticker) > 1 and ticker[:-1].isdigit() and ticker[-1].upper() == "T":
        return ticker[:-1]

    return ticker


def filing_thresholds(
    filing: FilingRecord | None,
    current_pct: float,
) -> tuple[float | None, float | None]:
    """Return (pct_to_next_upward, pct_to_next_downward) as decimals."""
    if filing is None:
        return None, None

    last = filing.last_filing

    if last is not None:
        up = (last + 0.01) - current_pct
        down = current_pct - (last - 0.01)
    else:
        up = 0.05 - current_pct
        down = None
    return up, down
