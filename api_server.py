"""FastAPI REST API for Paradaim Portfolio.Tool Trading V2.

Exposes the portfolio management logic as HTTP endpoints for the JavaFX frontend.
"""

from __future__ import annotations

import math
import os
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

import requests as http_requests

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from portfolio_tool.models import (
    CASH_SYMBOLS,
    DEFAULT_EXCHANGE_RATE,
    FilingRecord,
    FundPosition,
    Position,
    ProposedExecution,
    calculate_trade_from_raw,
    calculate_value_usd,
    filing_thresholds,
    normalize_symbol,
)

# ---------------------------------------------------------------------------
# J-Quants V2 API configuration
# ---------------------------------------------------------------------------
JQUANTS_API_KEY = "IsSPKDgnOojzoMEjBGhivJuw7_c9FBPlPDzt4iuYPdc"
JQUANTS_BASE_URL = "https://api.jquants.com/v2"


def _jquants_headers() -> dict[str, str]:
    return {"x-api-key": JQUANTS_API_KEY}


def _jquants_get(path: str, params: dict | None = None) -> dict:
    """Make an authenticated GET request to J-Quants V2 API."""
    resp = http_requests.get(
        f"{JQUANTS_BASE_URL}{path}",
        headers=_jquants_headers(),
        params=params or {},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_usd_jpy_rate() -> float | None:
    """Fetch current USD/JPY rate from a public API.  Returns None on failure."""
    try:
        resp = http_requests.get(
            "https://api.exchangerate-api.com/v4/latest/USD",
            timeout=10,
        )
        resp.raise_for_status()
        rate = resp.json().get("rates", {}).get("JPY")
        if rate and float(rate) > 1.0:
            return float(rate)
    except Exception as e:
        print(f"  FX rate fetch failed: {e}")
    return None


app = FastAPI(title="Paradaim Portfolio.Tool API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory state (single-user desktop companion)
# ---------------------------------------------------------------------------

_state: dict[str, Any] = {
    "portfolio": {},           # dict[str, Position]
    "fund_names": [],          # list[str]
    "usd_jpy_rate": 0.0,
    "filings": {},             # dict[str, FilingRecord]
    "proposed_executions": {}, # dict[str, ProposedExecution]
    "use_yfinance": False,
    "metrics": {},             # dict[str, dict] – per-symbol metrics from /fins/details
    "new_positions": set(),    # set[str] – symbols added via Add Position dialog
}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class FundPositionOut(BaseModel):
    quantity: float = 0.0
    pct_of_company: float = 0.0
    value_jpy: float = 0.0
    value_usd: float = 0.0
    weight: float = 0.0
    rel_weight: float = 0.0
    new_rel_weight: float = 0.0


class PositionOut(BaseModel):
    symbol: str
    name: str
    price: float
    is_cash: bool
    adv_10pct: float
    currency: str
    os_shares: float
    total_quantity: float
    total_pct_of_company: float
    inception_date: str = ""
    age_years: float | None = None
    funds: dict[str, FundPositionOut]
    # Metrics (populated by /api/metrics/refresh)
    pbr: float | None = None
    pe_ltm: float | None = None
    pe_ntm: float | None = None
    pe_24m: float | None = None
    peg_c: float | None = None
    peg_n: float | None = None
    roe_l: float | None = None
    roe_ntm: float | None = None
    plowback: float | None = None
    beta: float | None = None
    div_yield: float | None = None
    payout_ratio: float | None = None
    opm: float | None = None
    sales_cagr_2y: float | None = None
    op_cagr_2y: float | None = None
    eps_cagr_2y: float | None = None
    # Returns (populated by /api/metrics/refresh)
    ret_incep: float | None = None
    ret_1d: float | None = None
    ret_1w: float | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    ret_ytd: float | None = None
    ret_1y: float | None = None
    ret_3y: float | None = None
    ret_5y: float | None = None
    is_new: bool = False


class FilingOut(BaseModel):
    symbol: str
    name: str
    date: str | None
    last_filing: float | None
    pct_to_upward: float | None = None
    pct_to_downward: float | None = None


class ExecutionOut(BaseModel):
    key: str
    fund: str
    symbol: str
    name: str
    trade_type: str
    trade_quantity: float
    target_raw: float
    trade_value_usd: float
    trade_value_signed: float
    trading_days: float
    target_price: float | None
    pct_to_curr: float | None


class TradeRequest(BaseModel):
    fund: str
    symbol: str
    new_raw: float


class TradeResult(BaseModel):
    trade_type: str
    trade_quantity: float
    trade_value_jpy: float
    trade_value_usd: float


class AddPositionRequest(BaseModel):
    symbol: str
    name: str
    price: float
    is_cash: bool = False
    adv_10pct: float = 0.0
    currency: str = "JPY"
    os_shares: float = 0.0
    fund_quantities: dict[str, float] = {}
    # New fields for rel-weight-based addition
    fund_rel_weights: dict[str, float] = {}
    is_new_addition: bool = False


class SubmitTradeRequest(BaseModel):
    fund: str
    symbol: str
    trade_type: str
    target_raw: float
    trade_quantity: float
    trade_value_usd: float


class TargetPriceRequest(BaseModel):
    key: str
    target_price: float


class PortfolioSummary(BaseModel):
    num_positions: int
    fund_names: list[str]
    usd_jpy_rate: float
    total_value_jpy: float
    total_value_usd: float


class CashPathPoint(BaseModel):
    day: int
    label: str
    cash_mm: float


class CashPathSeries(BaseModel):
    symbol: str
    trade_type: str
    days: list[int]
    values: list[float]


class CashPathResponse(BaseModel):
    fund: str
    series: list[CashPathSeries]
    cash_path: list[CashPathPoint]
    current_cash_mm: float
    min_cash_mm: float
    ending_cash_mm: float


# ---------------------------------------------------------------------------
# Helper: recompute weights for the portfolio
# ---------------------------------------------------------------------------

def _recompute_weights() -> None:
    portfolio = _state["portfolio"]
    fund_names = _state["fund_names"]
    rate = _state["usd_jpy_rate"] or DEFAULT_EXCHANGE_RATE

    for fund_name in fund_names:
        total_value = 0.0
        securities_count = 0
        for pos in portfolio.values():
            fp = pos.funds.get(fund_name)
            if fp and fp.quantity > 0:
                value_jpy = pos.price * fp.quantity
                fp.value_jpy = value_jpy
                fp.value_usd = calculate_value_usd(value_jpy, rate)
                if not pos.is_cash:
                    total_value += value_jpy
                    securities_count += 1

                # Recalculate % of company from os_shares whenever available
                if pos.os_shares > 0 and not pos.is_cash:
                    fp.pct_of_company = fp.quantity / pos.os_shares

        avg_weight = 100.0 / securities_count if securities_count > 0 else 0.0

        for pos in portfolio.values():
            fp = pos.funds.get(fund_name)
            if fp and fp.quantity > 0 and not pos.is_cash:
                weight = (pos.price * fp.quantity / total_value * 100.0) if total_value > 0 else 0.0
                fp.weight = weight
                fp.rel_weight = weight / avg_weight if avg_weight > 0 else 0.0

                # Check if there is a proposed execution that sets new_rel_weight
                key = f"{fund_name}:{pos.symbol}"
                if key in _state["proposed_executions"]:
                    fp.new_rel_weight = _state["proposed_executions"][key].target_raw
                else:
                    fp.new_rel_weight = fp.rel_weight


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/status")
def status():
    return {"status": "ok", "name": "Paradaim Portfolio.Tool API"}


@app.get("/api/portfolio/summary", response_model=PortfolioSummary)
def portfolio_summary():
    portfolio = _state["portfolio"]
    rate = _state["usd_jpy_rate"] or DEFAULT_EXCHANGE_RATE
    total_jpy = sum(
        pos.price * pos.total_quantity for pos in portfolio.values()
    )
    return PortfolioSummary(
        num_positions=len(portfolio),
        fund_names=_state["fund_names"],
        usd_jpy_rate=_state["usd_jpy_rate"],
        total_value_jpy=total_jpy,
        total_value_usd=total_jpy / rate,
    )


@app.get("/api/portfolio/positions", response_model=list[PositionOut])
def list_positions():
    _recompute_weights()
    result = []
    for pos in _state["portfolio"].values():
        funds_out = {}
        for fn, fp in pos.funds.items():
            funds_out[fn] = FundPositionOut(
                quantity=fp.quantity,
                pct_of_company=fp.pct_of_company,
                value_jpy=fp.value_jpy,
                value_usd=fp.value_usd,
                weight=fp.weight,
                rel_weight=fp.rel_weight,
                new_rel_weight=fp.new_rel_weight,
            )
        metrics = _state["metrics"].get(pos.symbol, {})
        age = None
        if pos.inception_date:
            try:
                incep_dt = datetime.strptime(pos.inception_date, "%Y-%m-%d")
                delta = datetime.now() - incep_dt
                age = round(delta.days / 365.25, 1)
            except Exception:
                pass
        is_new = pos.symbol in _state.get("new_positions", set())
        result.append(PositionOut(
            symbol=pos.symbol,
            name=pos.name,
            price=pos.price,
            is_cash=pos.is_cash,
            adv_10pct=pos.adv_10pct,
            currency=pos.currency,
            os_shares=pos.os_shares,
            total_quantity=pos.total_quantity,
            total_pct_of_company=pos.calculate_pct_of_company(),
            inception_date=pos.inception_date,
            age_years=age,
            funds=funds_out,
            is_new=is_new,
            **{k: v for k, v in metrics.items() if k in PositionOut.model_fields},
        ))
    return result


@app.post("/api/portfolio/import")
async def import_portfolio(file: UploadFile = File(...)):
    """Import portfolio from an uploaded Excel file."""
    suffix = os.path.splitext(file.filename or "file.xlsx")[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        df = pd.read_excel(tmp_path)
        for col in ("Symbol", "Name", "Quantity"):
            if col not in df.columns:
                raise HTTPException(400, f"Required column '{col}' not found")

        has_fund = "Fund" in df.columns
        has_price = "Price" in df.columns
        has_adv = "10% 3m ADV" in df.columns
        has_os = "OS" in df.columns
        has_pct = "% of Company" in df.columns
        has_inception = "Inception" in df.columns

        portfolio: dict[str, Position] = {}
        usd_jpy_rate = 0.0

        fund_names = (
            df["Fund"].dropna().unique().tolist() if has_fund else ["Default"]
        )

        for _, row in df.iterrows():
            symbol = str(row["Symbol"]).strip()
            name = str(row["Name"]).strip()
            quantity = float(row["Quantity"])
            fund = str(row["Fund"]).strip() if has_fund else "Default"

            adv = float(row["10% 3m ADV"]) if has_adv and not pd.isna(row.get("10% 3m ADV")) else 0.0
            os_shares = float(row["OS"]) if has_os and not pd.isna(row.get("OS")) else 0.0
            pct = 0.0
            if has_pct and not pd.isna(row.get("% of Company")):
                pct = float(row["% of Company"])
            elif os_shares > 0 and quantity > 0:
                pct = quantity / os_shares

            if not symbol or pd.isna(symbol):
                continue

            is_cash = symbol.upper() in ("JPY", "USD")
            currency = symbol.upper() if is_cash else "JPY"

            price = 0.0
            if has_price and not pd.isna(row.get("Price")):
                price = float(row["Price"])
                if symbol.upper() == "JPY" and is_cash and price > 1.0:
                    usd_jpy_rate = price
            elif is_cash:
                price = 1.0

            inception_iso = ""
            if has_inception and not pd.isna(row.get("Inception")):
                try:
                    raw = row["Inception"]
                    if isinstance(raw, str):
                        dt = datetime.strptime(raw.strip(), "%m/%d/%Y")
                    else:
                        dt = pd.Timestamp(raw).to_pydatetime()
                    inception_iso = dt.strftime("%Y-%m-%d")
                except Exception:
                    pass

            if symbol not in portfolio:
                portfolio[symbol] = Position(
                    symbol=symbol, name=name, price=price,
                    is_cash=is_cash, adv_10pct=adv,
                    currency=currency, os_shares=os_shares,
                    inception_date=inception_iso,
                )
            portfolio[symbol].funds[fund] = FundPosition(
                quantity=quantity, pct_of_company=pct,
            )

        _state["portfolio"] = portfolio
        _state["fund_names"] = fund_names
        _state["usd_jpy_rate"] = usd_jpy_rate
        _state["proposed_executions"] = {}
        _state["new_positions"] = set()
        _recompute_weights()

        return {"message": f"Imported {len(portfolio)} positions across {len(fund_names)} fund(s)"}
    finally:
        os.unlink(tmp_path)


@app.post("/api/portfolio/position")
def add_position(req: AddPositionRequest):
    portfolio = _state["portfolio"]
    fund_names = _state["fund_names"]

    if req.is_cash:
        symbol = req.currency
        name = "Japanese Yen" if req.currency == "JPY" else "US Dollar"
        price = 1.0 if req.currency == "JPY" else (_state["usd_jpy_rate"] or DEFAULT_EXCHANGE_RATE)
    else:
        symbol = req.symbol
        name = req.name
        price = req.price

    pos = Position(
        symbol=symbol, name=name, price=price,
        is_cash=req.is_cash, adv_10pct=req.adv_10pct,
        currency=req.currency if req.is_cash else "JPY",
        os_shares=req.os_shares,
    )

    # Handle rel-weight-based addition (new position workflow)
    if req.fund_rel_weights and not req.is_cash and price > 0:
        rate = _state["usd_jpy_rate"] or DEFAULT_EXCHANGE_RATE
        for fn, rel_weight in req.fund_rel_weights.items():
            if fn not in fund_names:
                fund_names.append(fn)

            # Count existing securities and total value for this fund
            securities_count = 0
            total_portfolio_jpy = 0.0
            for p in portfolio.values():
                if p.is_cash:
                    continue
                fp = p.funds.get(fn)
                if fp and fp.quantity > 0:
                    securities_count += 1
                    total_portfolio_jpy += p.price * fp.quantity

            if securities_count == 0 or total_portfolio_jpy <= 0:
                continue

            # New position increases securities count by 1
            new_securities_count = securities_count + 1
            avg_weight = 100.0 / new_securities_count
            target_weight = rel_weight * avg_weight

            # Compute target position value and quantity
            # The new total portfolio value includes this new position
            # target_weight/100 = target_position_jpy / (total_portfolio_jpy + target_position_jpy)
            # Solving: target_position_jpy = target_weight * total_portfolio_jpy / (100 - target_weight)
            if target_weight >= 100:
                continue
            target_position_jpy = (target_weight / 100.0) * total_portfolio_jpy / (1.0 - target_weight / 100.0)
            trade_quantity = round(target_position_jpy / price)

            if trade_quantity <= 0:
                continue

            pos.funds[fn] = FundPosition(quantity=trade_quantity)

            trade_value_jpy = trade_quantity * price
            trade_value_usd = trade_value_jpy / rate
            adv = req.adv_10pct
            trading_days = abs(trade_value_usd) / adv if adv > 0 else 0.0

            key = f"{fn}:{symbol}"
            _state["proposed_executions"][key] = ProposedExecution(
                fund=fn,
                symbol=symbol,
                trade_type="Buy",
                trade_quantity=trade_quantity,
                target_raw=rel_weight,
                trade_value_usd=abs(trade_value_usd),
                trade_value_signed=abs(trade_value_usd),
                trading_days=trading_days,
            )
    else:
        for fn, qty in req.fund_quantities.items():
            pos.funds[fn] = FundPosition(quantity=qty)
            if fn not in fund_names:
                fund_names.append(fn)

    if req.is_new_addition:
        _state.setdefault("new_positions", set()).add(symbol)

    portfolio[symbol] = pos
    _recompute_weights()
    return {"message": f"Added position {symbol}"}


@app.delete("/api/portfolio/position/{symbol}")
def remove_position(symbol: str):
    portfolio = _state["portfolio"]
    if symbol not in portfolio:
        raise HTTPException(404, f"Position {symbol} not found")
    del portfolio[symbol]
    # Remove related executions
    to_remove = [k for k in _state["proposed_executions"] if k.endswith(f":{symbol}")]
    for k in to_remove:
        del _state["proposed_executions"][k]
    _recompute_weights()
    return {"message": f"Removed position {symbol}"}


@app.post("/api/trade/calculate", response_model=TradeResult | None)
def calculate_trade(req: TradeRequest):
    result = calculate_trade_from_raw(
        _state["portfolio"], req.fund, req.symbol, req.new_raw, _state["usd_jpy_rate"],
    )
    if result is None:
        raise HTTPException(400, "Cannot calculate trade")
    return TradeResult(**result)


@app.post("/api/trade/submit")
def submit_trade(req: SubmitTradeRequest):
    portfolio = _state["portfolio"]
    if req.symbol not in portfolio:
        raise HTTPException(404, f"Position {req.symbol} not found")

    position = portfolio[req.symbol]
    adv = position.adv_10pct

    trading_days = 0.0
    if adv > 0:
        trading_days = abs(req.trade_value_usd) / adv

    signed_value = abs(req.trade_value_usd) if req.trade_type == "Buy" else -abs(req.trade_value_usd)

    key = f"{req.fund}:{req.symbol}"
    _state["proposed_executions"][key] = ProposedExecution(
        fund=req.fund,
        symbol=req.symbol,
        trade_type=req.trade_type,
        trade_quantity=req.trade_quantity,
        target_raw=req.target_raw,
        trade_value_usd=abs(req.trade_value_usd),
        trade_value_signed=signed_value,
        trading_days=trading_days,
    )
    _recompute_weights()
    return {"message": f"Trade submitted: {key}", "key": key}


@app.get("/api/trades", response_model=list[ExecutionOut])
def list_trades():
    result = []
    for key, ex in _state["proposed_executions"].items():
        # Look up security name from portfolio
        pos = _state["portfolio"].get(ex.symbol)
        sec_name = pos.name if pos else ex.symbol
        result.append(ExecutionOut(
            key=key,
            fund=ex.fund,
            symbol=ex.symbol,
            name=sec_name,
            trade_type=ex.trade_type,
            trade_quantity=ex.trade_quantity,
            target_raw=ex.target_raw,
            trade_value_usd=ex.trade_value_usd,
            trade_value_signed=ex.trade_value_signed,
            trading_days=ex.trading_days,
            target_price=ex.target_price,
            pct_to_curr=ex.pct_to_curr,
        ))
    return result


@app.delete("/api/trades/{key}")
def delete_trade(key: str):
    if key not in _state["proposed_executions"]:
        raise HTTPException(404, f"Trade {key} not found")
    del _state["proposed_executions"][key]
    _recompute_weights()
    return {"message": f"Deleted trade {key}"}


@app.put("/api/trades/target-price")
def update_target_price(req: TargetPriceRequest):
    if req.key not in _state["proposed_executions"]:
        raise HTTPException(404, f"Trade {req.key} not found")
    ex = _state["proposed_executions"][req.key]
    ex.target_price = req.target_price
    pos = _state["portfolio"].get(ex.symbol)
    if pos and pos.price > 0:
        ex.pct_to_curr = ((req.target_price - pos.price) / pos.price) * 100.0
    return {"message": "Target price updated"}


@app.post("/api/filings/import")
async def import_filings(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename or "file.xlsx")[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        df = pd.read_excel(tmp_path)
        for col in ("Symbol", "Name", "Last Filing", "Date"):
            if col not in df.columns:
                raise HTTPException(400, f"Required column '{col}' not found")

        filings: dict[str, FilingRecord] = {}
        for _, row in df.iterrows():
            symbol = str(row["Symbol"]).strip()
            if not symbol or pd.isna(symbol):
                continue

            name = str(row["Name"]).strip()
            date = None
            if not pd.isna(row["Date"]):
                if isinstance(row["Date"], datetime):
                    date = row["Date"].strftime("%Y-%m-%d")
                else:
                    date = str(row["Date"]).strip()

            last_filing = _parse_filing_value(row["Last Filing"])
            filings[symbol] = FilingRecord(name=name, date=date, last_filing=last_filing)

        _state["filings"] = filings
        return {"message": f"Imported {len(filings)} filing records"}
    finally:
        os.unlink(tmp_path)


@app.get("/api/filings", response_model=list[FilingOut])
def list_filings():
    result = []
    portfolio = _state["portfolio"]
    for symbol, filing in _state["filings"].items():
        pos = portfolio.get(symbol)
        current_pct = pos.calculate_pct_of_company() if pos else 0.0
        up, down = filing_thresholds(filing, current_pct)
        result.append(FilingOut(
            symbol=symbol,
            name=filing.name,
            date=filing.date,
            last_filing=filing.last_filing,
            pct_to_upward=up,
            pct_to_downward=down,
        ))
    return result


@app.get("/api/cash-path/{fund}", response_model=CashPathResponse)
def cash_path(fund: str):
    portfolio = _state["portfolio"]
    executions = _state["proposed_executions"]
    rate = _state["usd_jpy_rate"] or DEFAULT_EXCHANGE_RATE

    fund_executions = [
        {"symbol": ex.symbol, "execution": ex}
        for ex in executions.values()
        if ex.fund == fund
    ]

    # Compute initial cash
    initial_cash_usd = 0.0
    for pos in portfolio.values():
        if pos.is_cash:
            fp = pos.funds.get(fund)
            if fp:
                if pos.currency == "USD":
                    initial_cash_usd += pos.price * fp.quantity
                else:
                    initial_cash_usd += pos.price * fp.quantity / rate

    # Compute max_days using dynamically calculated trading days
    computed_days = []
    for ex in executions.values():
        if ex.fund != fund:
            continue
        if ex.symbol in portfolio and portfolio[ex.symbol].adv_10pct > 0:
            td = abs(ex.trade_value_usd) / portfolio[ex.symbol].adv_10pct
        else:
            td = ex.trading_days
        if td:
            computed_days.append(int(math.ceil(td)))
    max_days = max(computed_days, default=5)
    max_days = max(max_days + 1, 5)

    daily_cash_flow = [0.0] * max_days
    cash_position = [initial_cash_usd / 1_000_000]

    series_list = []
    for item in fund_executions:
        symbol = item["symbol"]
        ex: ProposedExecution = item["execution"]
        if symbol not in portfolio:
            continue

        pos = portfolio[symbol]
        adv = pos.adv_10pct

        # Dynamically compute trading days from current ADV
        if adv > 0:
            trading_days = abs(ex.trade_value_usd) / adv
        else:
            trading_days = ex.trading_days
        if not trading_days:
            continue

        is_buy = ex.trade_type == "Buy"
        full_days = math.floor(trading_days)
        last_frac = trading_days - full_days
        daily_amount = adv / 1_000_000 if adv > 0 else (abs(ex.trade_value_usd) / trading_days / 1_000_000)

        days = []
        values = []
        for day in range(1, full_days + 1):
            value = -daily_amount if is_buy else daily_amount
            days.append(day)
            values.append(value)
            daily_cash_flow[day - 1] += value

        if last_frac > 0:
            day = full_days + 1
            remaining = daily_amount * last_frac
            value = -remaining if is_buy else remaining
            days.append(day)
            values.append(value)
            if day - 1 < len(daily_cash_flow):
                daily_cash_flow[day - 1] += value

        series_list.append(CashPathSeries(
            symbol=symbol, trade_type=ex.trade_type,
            days=days, values=values,
        ))

    path_points = []
    path_points.append(CashPathPoint(day=0, label="Initial", cash_mm=cash_position[0]))
    for i, flow in enumerate(daily_cash_flow):
        cash_position.append(cash_position[-1] + flow)
        path_points.append(CashPathPoint(day=i + 1, label=str(i + 1), cash_mm=cash_position[-1]))

    return CashPathResponse(
        fund=fund,
        series=series_list,
        cash_path=path_points,
        current_cash_mm=initial_cash_usd / 1_000_000,
        min_cash_mm=min(cash_position),
        ending_cash_mm=cash_position[-1],
    )


@app.post("/api/prices/refresh")
def refresh_prices():
    """Refresh prices and ADV data using J-Quants V2 API."""
    portfolio = _state["portfolio"]
    updated = 0
    adv_updated = 0
    errors = []

    # Fetch current USD/JPY rate
    live_rate = _fetch_usd_jpy_rate()
    if live_rate:
        _state["usd_jpy_rate"] = live_rate
        print(f"  USD/JPY rate updated: {live_rate:.2f}")

    # Date range for 3-month ADV calculation
    today = datetime.now()
    date_to = today.strftime("%Y%m%d")
    date_from = (today - timedelta(days=90)).strftime("%Y%m%d")

    # Collect non-cash symbols
    symbols = [s for s, p in portfolio.items() if not p.is_cash]

    def _fetch_price(symbol: str) -> dict:
        """Fetch daily bars for a single symbol. Returns result dict."""
        code = f"{symbol}0"
        data = _jquants_get("/equities/bars/daily", {
            "code": code,
            "from": date_from,
            "to": date_to,
        })
        return {"symbol": symbol, "data": data}

    # Fetch all symbols in parallel (Premium rate limits allow higher concurrency)
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_fetch_price, s): s for s in symbols}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                results.append(future.result())
            except Exception as e:
                print(f"  {sym}: ERROR {e}")
                errors.append(f"{sym}: {e}")

    for result in results:
        symbol = result["symbol"]
        position = portfolio[symbol]
        data = result["data"]
        try:
            # V2 response uses "data" key
            bars = data.get("data") or data.get("eq_bars_daily") or []
            if not bars:
                print(f"  {symbol}: no bars returned from J-Quants")
                errors.append(f"{symbol}: no data")
                continue

            # Latest bar for current price
            latest = bars[-1]
            # V2 may use abbreviated field names (C, Vo) or full names (Close, Volume)
            price = latest.get("Close") or latest.get("AdjClose") or latest.get("C") or latest.get("AdjC")
            if price is not None:
                position.price = float(price)
                updated += 1
                print(f"  {symbol}: price={position.price:,.0f}")

            # Compute 3-month average daily volume for ADV
            volumes = []
            for bar in bars:
                vol = bar.get("Volume") or bar.get("AdjVo") or bar.get("Vo") or 0
                if vol and float(vol) > 0:
                    volumes.append(float(vol))

            if volumes and position.price > 0:
                avg_vol = sum(volumes) / len(volumes)
                rate = _state["usd_jpy_rate"] or DEFAULT_EXCHANGE_RATE
                adv_value_usd = (avg_vol * 0.10 * position.price) / rate
                position.adv_10pct = adv_value_usd
                adv_updated += 1
                print(f"  {symbol}: 10%ADV = {adv_value_usd:,.0f} USD "
                      f"(avg_vol={avg_vol:,.0f} x price={position.price:,.0f} / rate={rate:.2f})")
            else:
                print(f"  {symbol}: WARNING no volume data in {len(bars)} bars")
        except Exception as e:
            print(f"  {symbol}: ERROR {e}")
            errors.append(f"{symbol}: {e}")

    # Recompute trading_days for existing proposed executions with updated ADV
    for key, ex in _state["proposed_executions"].items():
        if ex.symbol in portfolio:
            adv = portfolio[ex.symbol].adv_10pct
            if adv > 0:
                ex.trading_days = abs(ex.trade_value_usd) / adv

    _recompute_weights()
    msg = f"Updated {updated} prices, {adv_updated} ADV values (J-Quants V2)"
    if errors:
        msg += f" | {len(errors)} errors"
    print(f"Price refresh complete: {msg}")
    return {"message": msg, "usd_jpy_rate": _state["usd_jpy_rate"], "errors": errors}


@app.post("/api/metrics/refresh")
def refresh_metrics():
    """Refresh fundamental metrics using J-Quants V2 Premium /fins/details and /indices/bars/daily/topix."""
    import numpy as np

    portfolio = _state["portfolio"]
    symbols = [s for s, p in portfolio.items() if not p.is_cash]
    updated = 0
    errors = []

    today = datetime.now()
    date_to = today.strftime("%Y%m%d")
    # Determine earliest inception date across portfolio to ensure full coverage
    earliest_inception = None
    for pos in portfolio.values():
        if pos.inception_date:
            try:
                d = datetime.strptime(pos.inception_date, "%Y-%m-%d")
                if earliest_inception is None or d < earliest_inception:
                    earliest_inception = d
            except Exception:
                pass
    # Use earliest inception or 5 years, whichever is further back
    default_from = today - timedelta(days=365 * 5 + 2)
    date_from_bars = min(earliest_inception or default_from, default_from)
    date_from_bars_str = (date_from_bars - timedelta(days=7)).strftime("%Y%m%d")  # small buffer
    date_from_1y = (today - timedelta(days=365)).strftime("%Y%m%d")

    # ---- Fetch TOPIX daily bars for beta calculation ----
    topix_returns = []
    topix_closes_by_date: dict[str, float] = {}
    try:
        topix_data = _jquants_get("/indices/bars/daily/topix", {
            "from": date_from_1y,
            "to": date_to,
        })
        topix_bars = topix_data.get("data") or topix_data.get("idx_bars_daily_topix") or []
        if topix_bars:
            topix_closes = []
            for bar in topix_bars:
                dt = bar.get("Date", "")
                c = bar.get("Close") or bar.get("C")
                if c is not None:
                    try:
                        val = float(c)
                        topix_closes.append(val)
                        if dt:
                            topix_closes_by_date[dt] = val
                    except (ValueError, TypeError):
                        pass
            if len(topix_closes) >= 2:
                topix_arr = np.array(topix_closes)
                topix_returns = list((topix_arr[1:] - topix_arr[:-1]) / topix_arr[:-1])
        print(f"  TOPIX: {len(topix_returns)} daily returns loaded")
    except Exception as e:
        print(f"  TOPIX fetch error: {e}")

    # ---- Parallel fetch: fins/details + fins/summary + stock bars for all symbols ----
    def _fetch_symbol_data(symbol: str) -> dict:
        code = f"{symbol}0"
        detail_data = _jquants_get("/fins/details", {"code": code})
        summary_data = _jquants_get("/fins/summary", {"code": code})
        stock_data = _jquants_get("/equities/bars/daily", {
            "code": code,
            "from": date_from_bars_str,
            "to": date_to,
        })
        return {"symbol": symbol, "detail_data": detail_data, "summary_data": summary_data, "stock_data": stock_data}

    prefetched: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_fetch_symbol_data, s): s for s in symbols}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                prefetched[sym] = future.result()
            except Exception as e:
                print(f"  {sym}: ERROR fetching data: {e}")
                errors.append(f"{sym}: {e}")

    for symbol in symbols:
        if symbol not in prefetched:
            continue
        position = portfolio[symbol]
        fetched = prefetched[symbol]
        m: dict[str, Any] = {}

        try:
            # ---- Parse /fins/details (Premium endpoint with full BS/PL/CF) ----
            detail_data = fetched["detail_data"]
            records = detail_data.get("data") or detail_data.get("fs_details") or []
            if not records:
                print(f"  {symbol}: no fins/details data")
                errors.append(f"{symbol}: no details")
                continue

            # Sort by disclosed date descending (most recent first)
            records.sort(key=lambda r: r.get("DiscDate", ""), reverse=True)

            # Parse each record into a normalised dict with DocType metadata
            parsed_records = []
            for rec in records:
                doc_type = rec.get("DocType", "")
                fs = rec.get("FS") or {}
                norm = _extract_fs_values(fs)
                # Determine period type from DocType (e.g. "FYFinancialStatements_...")
                period_type = _parse_period_type(doc_type)
                norm["_period_type"] = period_type
                norm["_disc_date"] = rec.get("DiscDate", "")
                norm["_doc_type"] = doc_type
                # Extract fiscal year end from DEI if available
                fy_end = fs.get("Current fiscal year end date, DEI") or fs.get("Current period end date, DEI") or ""
                norm["_fy_end"] = fy_end
                parsed_records.append(norm)

            latest = parsed_records[0]

            # Find latest FY record
            fy_record = None
            for pr in parsed_records:
                if pr["_period_type"] == "FY":
                    fy_record = pr
                    break

            price = position.price
            os_shares = position.os_shares

            # ---- Parse /fins/summary for FEPS, NxFEPS, FNP etc. and os_shares ----
            summary_data = fetched.get("summary_data", {})
            # Try multiple possible response wrapper keys
            summary_records = (
                summary_data.get("data")
                or summary_data.get("fs_summary")
                or summary_data.get("statements")
                or summary_data.get("fins_summary")
                or []
            )
            if not summary_records and isinstance(summary_data, list):
                summary_records = summary_data  # response might be a bare list

            # Sort by DiscDate descending (most recent first)
            summary_records.sort(key=lambda r: r.get("DiscDate", ""), reverse=True)

            # Helper to extract a float from a record
            def _sfloat(rec: dict, key: str) -> float | None:
                v = rec.get(key)
                if v is None:
                    return None
                try:
                    return float(v)
                except (ValueError, TypeError):
                    return None

            # Scan records to find the most recent one that has FEPS populated
            # (not all filings include forecasts; quarterly updates usually do)
            summary_feps: float | None = None
            summary_nxfeps: float | None = None
            summary_fnp: float | None = None
            summary_nxfnp: float | None = None
            summary_eq: float | None = None
            summary_eps: float | None = None
            summary_bps: float | None = None
            summary_roe: float | None = None

            for srec in summary_records:
                # Pick first record that has FEPS for forward PE
                if summary_feps is None:
                    v = _sfloat(srec, "FEPS")
                    if v is not None and v > 0:
                        summary_feps = v
                        # Grab related fields from same record for consistency
                        if summary_fnp is None:
                            summary_fnp = _sfloat(srec, "FNP")
                        if summary_nxfeps is None:
                            summary_nxfeps = _sfloat(srec, "NxFEPS")
                        if summary_nxfnp is None:
                            summary_nxfnp = _sfloat(srec, "NxFNp")
                # Pick equity from first record that has it
                if summary_eq is None:
                    summary_eq = _sfloat(srec, "Eq")
                # Pick EPS/BPS/ROE as fallbacks
                if summary_eps is None:
                    summary_eps = _sfloat(srec, "EPS")
                if summary_bps is None:
                    summary_bps = _sfloat(srec, "BPS")
                if summary_roe is None:
                    summary_roe = _sfloat(srec, "ROE")
                # Also scan for NxFEPS in other records if not found yet
                if summary_nxfeps is None:
                    v = _sfloat(srec, "NxFEPS")
                    if v is not None and v > 0:
                        summary_nxfeps = v
                        if summary_nxfnp is None:
                            summary_nxfnp = _sfloat(srec, "NxFNp")

            # Auto-populate os_shares from summary if not set from XLS
            if os_shares <= 0 and summary_records:
                for srec in summary_records:
                    val = srec.get("NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock")
                    if val is None:
                        val = srec.get("NumSharesOutstanding")
                    if val is not None:
                        try:
                            candidate = float(val)
                            if candidate > 0:
                                os_shares = candidate
                                position.os_shares = os_shares
                                print(f"  {symbol}: os_shares auto-populated from summary: {os_shares:,.0f}")
                                break
                        except (ValueError, TypeError):
                            pass

            if summary_records:
                print(f"  {symbol}: summary has {len(summary_records)} records, "
                      f"keys={list(summary_records[0].keys())[:10]}..., "
                      f"FEPS={summary_feps}, NxFEPS={summary_nxfeps}, "
                      f"FNP={summary_fnp}, EPS={summary_eps}, ROE={summary_roe}")
            else:
                print(f"  {symbol}: NO summary records (raw keys={list(summary_data.keys()) if isinstance(summary_data, dict) else 'list'})")

            # ---- PBR: Price / (Equity / Shares) ----
            equity = None
            for pr in parsed_records:
                if pr.get("equity") is not None:
                    equity = pr["equity"]
                    break
            if equity is None and summary_eq and summary_eq > 0:
                equity = summary_eq
            if equity and equity > 0 and os_shares > 0 and price > 0:
                bvps = equity / os_shares
                m["pbr"] = round(price / bvps, 2)

            # ---- PE LTM: Price / (Net Income FY / Shares), fallback to summary EPS ----
            net_income_fy = fy_record.get("net_income") if fy_record else None
            if net_income_fy and net_income_fy > 0 and os_shares > 0 and price > 0:
                ltm_eps = net_income_fy / os_shares
                m["pe_ltm"] = round(price / ltm_eps, 1)
            elif summary_eps and summary_eps > 0 and price > 0:
                m["pe_ltm"] = round(price / summary_eps, 1)

            # ---- PE NTM: use /fins/summary FEPS first, fall back to details forecast ----
            forecast_ni = None
            for pr in parsed_records:
                if pr.get("forecast_net_income") is not None:
                    forecast_ni = pr["forecast_net_income"]
                    break
            # Prefer summary FEPS (per-share, more reliably populated)
            if summary_feps and summary_feps > 0 and price > 0:
                m["pe_ntm"] = round(price / summary_feps, 1)
            elif forecast_ni and forecast_ni > 0 and os_shares > 0 and price > 0:
                feps = forecast_ni / os_shares
                m["pe_ntm"] = round(price / feps, 1)

            # ---- PE 24M: use /fins/summary NxFEPS first, fall back to details ----
            next_yr_ni = None
            for pr in parsed_records:
                if pr.get("next_yr_forecast_ni") is not None:
                    next_yr_ni = pr["next_yr_forecast_ni"]
                    break
            if summary_nxfeps and summary_nxfeps > 0 and price > 0:
                m["pe_24m"] = round(price / summary_nxfeps, 1)
            elif next_yr_ni and next_yr_ni > 0 and os_shares > 0 and price > 0:
                next_yr_eps = next_yr_ni / os_shares
                m["pe_24m"] = round(price / next_yr_eps, 1)

            # ---- EPS CAGR from historical FY data ----
            historical_eps_vals = _collect_annual_values_details(parsed_records, "net_income", os_shares)
            eps_growth = _compute_cagr(historical_eps_vals)

            # ---- PEGc: PE NTM / EPS growth ----
            # Prefer historical CAGR; fall back to summary EPS→FEPS 1Y growth
            pe_for_peg = m.get("pe_ntm") or m.get("pe_ltm")
            effective_eps_growth = eps_growth
            if effective_eps_growth is None and summary_eps and summary_feps and summary_eps > 0:
                effective_eps_growth = (summary_feps - summary_eps) / abs(summary_eps)
            if pe_for_peg and effective_eps_growth and effective_eps_growth > 0:
                m["peg_c"] = round(pe_for_peg / (effective_eps_growth * 100), 2)

            # ---- PEG n: PE 24M / next year EPS growth ----
            # Prefer summary FEPS→NxFEPS growth, fall back to details forecast_ni→next_yr_ni
            if m.get("pe_24m"):
                ntm_eps_for_peg = summary_feps
                nxtm_eps_for_peg = summary_nxfeps
                if ntm_eps_for_peg and nxtm_eps_for_peg and ntm_eps_for_peg > 0:
                    next_yr_growth = (nxtm_eps_for_peg - ntm_eps_for_peg) / abs(ntm_eps_for_peg)
                    if next_yr_growth > 0:
                        m["peg_n"] = round(m["pe_24m"] / (next_yr_growth * 100), 2)
                elif forecast_ni and next_yr_ni and forecast_ni > 0:
                    next_yr_growth = (next_yr_ni - forecast_ni) / abs(forecast_ni)
                    if next_yr_growth > 0:
                        m["peg_n"] = round(m["pe_24m"] / (next_yr_growth * 100), 2)

            # ---- ROE (l): Net Income / Equity ----
            ni_for_roe = None
            for pr in parsed_records:
                if pr.get("net_income") is not None:
                    ni_for_roe = pr["net_income"]
                    break
            if ni_for_roe is not None and equity and equity > 0:
                m["roe_l"] = round(ni_for_roe / equity * 100, 1)
            elif summary_roe is not None:
                m["roe_l"] = round(summary_roe, 1)

            # ---- ROE NTM: Forecast NI / Equity (prefer summary FNP) ----
            roe_ntm_ni = summary_fnp if summary_fnp is not None else forecast_ni
            if roe_ntm_ni is not None and equity and equity > 0:
                m["roe_ntm"] = round(roe_ntm_ni / equity * 100, 1)
            elif summary_roe is not None and summary_feps and summary_eps and summary_eps > 0:
                # Approximate: scale ROE by forecast/actual EPS ratio
                m["roe_ntm"] = round(summary_roe * (summary_feps / summary_eps), 1)

            # ---- Plowback & Payout: from dividends paid / net income ----
            dividends_paid = None
            for pr in parsed_records:
                if pr.get("dividends_paid") is not None:
                    dividends_paid = abs(pr["dividends_paid"])
                    break
            if dividends_paid is not None and ni_for_roe and ni_for_roe > 0:
                payout_dec = dividends_paid / ni_for_roe
                if payout_dec <= 2.0:  # sanity check
                    m["plowback"] = round(1.0 - payout_dec, 3)
                    m["payout_ratio"] = round(payout_dec * 100, 1)

            # ---- Div Yield: Dividends Paid / Market Cap ----
            if dividends_paid is not None and os_shares > 0 and price > 0:
                div_per_share = dividends_paid / os_shares
                m["div_yield"] = round(div_per_share / price * 100, 2)

            # ---- OPM: Operating Profit / Net Sales ----
            op_profit = None
            net_sales = None
            for pr in parsed_records:
                if op_profit is None and pr.get("operating_profit") is not None:
                    op_profit = pr["operating_profit"]
                if net_sales is None and pr.get("net_sales") is not None:
                    net_sales = pr["net_sales"]
                if op_profit is not None and net_sales is not None:
                    break
            if op_profit is not None and net_sales and net_sales > 0:
                m["opm"] = round(op_profit / net_sales * 100, 1)

            # ---- 2Y Sales CAGR ----
            historical_sales = _collect_annual_values_details(parsed_records, "net_sales")
            sales_cagr = _compute_cagr(historical_sales)
            if sales_cagr is not None:
                m["sales_cagr_2y"] = round(sales_cagr * 100, 1)

            # ---- 2Y Op CAGR ----
            historical_op = _collect_annual_values_details(parsed_records, "operating_profit")
            op_cagr = _compute_cagr(historical_op)
            if op_cagr is not None:
                m["op_cagr_2y"] = round(op_cagr * 100, 1)

            # ---- 2Y EPS CAGR ----
            if eps_growth is not None:
                m["eps_cagr_2y"] = round(eps_growth * 100, 1)

            # ---- Beta (rolling regression vs TOPIX) ----
            if topix_closes_by_date:
                try:
                    stock_bars = fetched["stock_data"].get("data") or fetched["stock_data"].get("eq_bars_daily") or []
                    if stock_bars:
                        stock_closes_by_date: dict[str, float] = {}
                        for bar in stock_bars:
                            dt = bar.get("Date", "")
                            c = bar.get("Close") or bar.get("AdjClose") or bar.get("C") or bar.get("AdjC")
                            if c is not None and dt:
                                try:
                                    stock_closes_by_date[dt] = float(c)
                                except (ValueError, TypeError):
                                    pass

                        common_dates = sorted(set(stock_closes_by_date.keys()) & set(topix_closes_by_date.keys()))
                        if len(common_dates) >= 30:
                            s_prices = np.array([stock_closes_by_date[d] for d in common_dates])
                            t_prices = np.array([topix_closes_by_date[d] for d in common_dates])
                            s_ret = (s_prices[1:] - s_prices[:-1]) / s_prices[:-1]
                            t_ret = (t_prices[1:] - t_prices[:-1]) / t_prices[:-1]
                            cov = np.cov(s_ret, t_ret)
                            if cov[1, 1] > 0:
                                beta_val = cov[0, 1] / cov[1, 1]
                                m["beta"] = round(float(beta_val), 2)
                except Exception as e:
                    print(f"  {symbol}: beta calc error: {e}")

            # ---- Price returns (1d, 1w, 1m, 3m, 6m, YTD, 1y, 3y, 5y) ----
            try:
                stock_bars = fetched["stock_data"].get("data") or fetched["stock_data"].get("eq_bars_daily") or []
                if stock_bars:
                    closes_by_date: dict[str, float] = {}
                    for bar in stock_bars:
                        dt = bar.get("Date", "")
                        c = bar.get("AdjClose") or bar.get("Close") or bar.get("AdjC") or bar.get("C")
                        if c is not None and dt:
                            try:
                                closes_by_date[dt] = float(c)
                            except (ValueError, TypeError):
                                pass
                    if closes_by_date:
                        sorted_dates = sorted(closes_by_date.keys())
                        latest_price = closes_by_date[sorted_dates[-1]]

                        def _find_price_on_or_before(target_date_str: str) -> float | None:
                            """Find closing price on target date or nearest prior date."""
                            for d in reversed(sorted_dates):
                                if d <= target_date_str:
                                    return closes_by_date[d]
                            return None

                        def _calc_return(days_ago: int) -> float | None:
                            target = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")
                            p = _find_price_on_or_before(target)
                            if p and p > 0:
                                return round((latest_price - p) / p * 100, 2)
                            return None

                        m["ret_1d"] = _calc_return(1)
                        m["ret_1w"] = _calc_return(7)
                        m["ret_1m"] = _calc_return(30)
                        m["ret_3m"] = _calc_return(91)
                        m["ret_6m"] = _calc_return(182)
                        m["ret_1y"] = _calc_return(365)
                        m["ret_3y"] = _calc_return(365 * 3)
                        m["ret_5y"] = _calc_return(365 * 5)

                        # YTD: from last trading day of previous year
                        ytd_target = f"{today.year - 1}-12-31"
                        ytd_price = _find_price_on_or_before(ytd_target)
                        if ytd_price and ytd_price > 0:
                            m["ret_ytd"] = round((latest_price - ytd_price) / ytd_price * 100, 2)

                        # Since inception return
                        if position.inception_date:
                            incep_price = _find_price_on_or_before(position.inception_date)
                            if incep_price and incep_price > 0:
                                m["ret_incep"] = round((latest_price - incep_price) / incep_price * 100, 2)
            except Exception as e:
                print(f"  {symbol}: returns calc error: {e}")

            _state["metrics"][symbol] = m
            updated += 1
            missing = [k for k in ["pe_ntm", "pe_24m", "peg_c", "peg_n", "roe_ntm"] if k not in m]
            summary_info = f"FEPS={summary_feps} NxFEPS={summary_nxfeps} FNP={summary_fnp}"
            print(f"  {symbol}: {len(m)} metrics | summary: {summary_info} | missing: {missing or 'none'}")

        except Exception as e:
            print(f"  {symbol}: ERROR {e}")
            errors.append(f"{symbol}: {e}")

    _recompute_weights()
    msg = f"Updated metrics for {updated} positions (J-Quants V2 Premium /fins/details)"
    if errors:
        msg += f" | {len(errors)} errors"
    print(f"Metrics refresh complete: {msg}")
    return {"message": msg, "errors": errors}


# ---------------------------------------------------------------------------
# EDINET label pattern matching for /fins/details FS dict
# ---------------------------------------------------------------------------

# Patterns to search for in FS dict keys (case-insensitive substring match).
# Order matters: first match wins, so put more specific patterns first.
_FS_LABEL_MAP: list[tuple[str, list[str]]] = [
    # Balance sheet
    ("total_assets", [
        "total assets",
    ]),
    ("equity", [
        "shareholders' equity",
        "shareholders equity",
        "equity attributable to owners of parent",
        "total equity",
        "net assets",
    ]),
    # Income statement
    ("net_sales", [
        "net sales",
        "revenue",
        "operating revenue",
    ]),
    ("operating_profit", [
        "operating profit",
        "operating income",
    ]),
    ("ordinary_profit", [
        "ordinary profit",
        "ordinary income",
    ]),
    ("net_income", [
        "profit attributable to owners of parent",
        "profit (loss) attributable to owners of parent",
        "net income attributable",
        "profit for the period attributable to owners of parent",
        "net income",
        "profit for the period",
        "profit (loss)",
    ]),
    # Cash flow
    ("cfo", [
        "cash flows from operating",
        "net cash provided by operating",
    ]),
    ("cfi", [
        "cash flows from investing",
        "net cash used in investing",
    ]),
    ("cff", [
        "cash flows from financing",
        "net cash used in financing",
    ]),
    ("dividends_paid", [
        "dividends paid",
        "cash dividends paid",
    ]),
    # Per-share (sometimes in details)
    ("eps_detail", [
        "basic earnings per share",
        "earnings per share",
    ]),
    ("bps_detail", [
        "book value per share",
        "net assets per share",
    ]),
    # Forecast (some filings embed forecasts)
    ("forecast_net_income", [
        "forecast of net income",
        "forecast of profit attributable",
        "forecast net income",
        "forecast profit",
    ]),
    ("forecast_sales", [
        "forecast of net sales",
        "forecast of revenue",
        "forecast net sales",
        "forecast revenue",
    ]),
    ("next_yr_forecast_ni", [
        "next fiscal year forecast of net income",
        "next fiscal year forecast of profit",
        "next year forecast net income",
    ]),
]


def _extract_fs_values(fs: dict) -> dict[str, float | None]:
    """Extract normalised financial values from an EDINET FS dict.

    The FS dict has verbose EDINET labels as keys (English) and string values.
    We match labels case-insensitively against known patterns.
    """
    result: dict[str, float | None] = {}
    if not fs:
        return result

    # Build lowercase key->value map, parsing numeric values
    lc_items: list[tuple[str, float]] = []
    for key, val in fs.items():
        if val is None or isinstance(val, dict):
            continue
        try:
            fval = float(str(val).replace(",", ""))
            lc_items.append((key.lower(), fval))
        except (ValueError, TypeError):
            pass

    matched_concepts: set[str] = set()
    for concept, patterns in _FS_LABEL_MAP:
        if concept in matched_concepts:
            continue
        for pattern in patterns:
            for lc_key, fval in lc_items:
                if pattern in lc_key:
                    result[concept] = fval
                    matched_concepts.add(concept)
                    break
            if concept in matched_concepts:
                break

    return result


def _parse_period_type(doc_type: str) -> str:
    """Extract period type (FY, 3Q, 2Q, 1Q) from DocType string."""
    dt_upper = doc_type.upper()
    if dt_upper.startswith("FY") or "ANNUAL" in dt_upper:
        return "FY"
    if dt_upper.startswith("3Q") or "THIRDQUARTER" in dt_upper:
        return "3Q"
    if dt_upper.startswith("2Q") or "SECONDQUARTER" in dt_upper or "INTERIM" in dt_upper:
        return "2Q"
    if dt_upper.startswith("1Q") or "FIRSTQUARTER" in dt_upper:
        return "1Q"
    return "OTHER"


def _collect_annual_values_details(
    parsed_records: list[dict], field: str,
    divide_by_shares: float = 0.0,
) -> list[tuple[str, float]]:
    """Collect (fiscal_year_end, value) pairs from FY records for CAGR calculation."""
    values = []
    seen_years: set[str] = set()
    for pr in parsed_records:
        if pr.get("_period_type") != "FY":
            continue
        fy_end = pr.get("_fy_end", "")
        if not fy_end or fy_end in seen_years:
            continue
        val = pr.get(field)
        if val is not None and val > 0:
            if divide_by_shares > 0:
                val = val / divide_by_shares
            values.append((fy_end, val))
            seen_years.add(fy_end)
    values.sort(key=lambda x: x[0])
    return values


def _compute_cagr(values: list[tuple[str, float]]) -> float | None:
    """Compute CAGR from a list of (date_str, value) pairs. Needs at least 2 values ~2 years apart."""
    if len(values) < 2:
        return None
    oldest = values[0][1]
    newest = values[-1][1]
    if oldest <= 0 or newest <= 0:
        return None
    # Number of years between first and last
    try:
        d0 = datetime.strptime(values[0][0], "%Y-%m-%d")
        d1 = datetime.strptime(values[-1][0], "%Y-%m-%d")
        years = (d1 - d0).days / 365.25
    except Exception:
        years = len(values) - 1
    if years <= 0:
        return None
    return (newest / oldest) ** (1.0 / years) - 1.0


@app.get("/api/stock/lookup/{symbol}")
def stock_lookup(symbol: str):
    """Fetch name, price, ADV, and os_shares for a single stock from J-Quants."""
    code = f"{symbol}0"
    today = datetime.now()
    date_to = today.strftime("%Y%m%d")
    date_from = (today - timedelta(days=90)).strftime("%Y%m%d")
    rate = _state["usd_jpy_rate"] or DEFAULT_EXCHANGE_RATE

    result: dict[str, Any] = {"symbol": symbol}
    errors = []

    # Fetch listed info for company name
    try:
        info_data = _jquants_get("/listed/info", {"code": code})
        info_records = info_data.get("info") or []
        if info_records:
            latest_info = info_records[-1]
            result["name"] = latest_info.get("CompanyNameEnglish") or latest_info.get("CompanyName") or ""
        else:
            result["name"] = ""
    except Exception as e:
        result["name"] = ""
        errors.append(f"listed/info: {e}")

    # Fetch daily bars for price and ADV
    try:
        bar_data = _jquants_get("/equities/bars/daily", {
            "code": code, "from": date_from, "to": date_to,
        })
        bars = bar_data.get("data") or bar_data.get("eq_bars_daily") or []
        if bars:
            latest = bars[-1]
            price = latest.get("Close") or latest.get("AdjClose") or latest.get("C") or latest.get("AdjC")
            result["price"] = float(price) if price is not None else 0.0

            volumes = []
            for bar in bars:
                vol = bar.get("Volume") or bar.get("AdjVo") or bar.get("Vo") or 0
                if vol and float(vol) > 0:
                    volumes.append(float(vol))
            if volumes and result["price"] > 0:
                avg_vol = sum(volumes) / len(volumes)
                result["adv_10pct"] = (avg_vol * 0.10 * result["price"]) / rate
            else:
                result["adv_10pct"] = 0.0
        else:
            result["price"] = 0.0
            result["adv_10pct"] = 0.0
            errors.append("no daily bars")
    except Exception as e:
        result["price"] = 0.0
        result["adv_10pct"] = 0.0
        errors.append(f"bars: {e}")

    # Fetch /fins/summary for outstanding shares
    try:
        summary_data = _jquants_get("/fins/summary", {"code": code})
        summary_records = (
            summary_data.get("data")
            or summary_data.get("fs_summary")
            or summary_data.get("statements")
            or summary_data.get("fins_summary")
            or []
        )
        if not summary_records and isinstance(summary_data, list):
            summary_records = summary_data
        summary_records.sort(key=lambda r: r.get("DiscDate", ""), reverse=True)

        os_shares = 0.0
        for srec in summary_records:
            val = srec.get("NumberOfIssuedAndOutstandingSharesAtTheEndOfFiscalYearIncludingTreasuryStock")
            if val is None:
                val = srec.get("NumSharesOutstanding")
            if val is not None:
                try:
                    os_shares = float(val)
                    if os_shares > 0:
                        break
                except (ValueError, TypeError):
                    pass
        result["os_shares"] = os_shares
    except Exception as e:
        result["os_shares"] = 0.0
        errors.append(f"fins/summary: {e}")

    if errors:
        result["errors"] = errors
    return result


@app.get("/api/debug/adv")
def debug_adv():
    """Diagnostic endpoint to check ADV values for all positions."""
    portfolio = _state["portfolio"]
    result = []
    for symbol, pos in portfolio.items():
        if pos.is_cash:
            continue
        result.append({
            "symbol": symbol,
            "price": pos.price,
            "adv_10pct": pos.adv_10pct,
            "has_adv": pos.adv_10pct > 0,
        })
    executions = []
    for key, ex in _state["proposed_executions"].items():
        executions.append({
            "key": key,
            "trade_value_usd": ex.trade_value_usd,
            "trading_days": ex.trading_days,
            "adv_10pct": portfolio[ex.symbol].adv_10pct if ex.symbol in portfolio else 0,
        })
    return {"positions": result, "executions": executions}


@app.get("/api/debug/jquants/{symbol}")
def debug_jquants(symbol: str):
    """Test J-Quants V2 API response for a single stock."""
    code = f"{symbol}0"
    today = datetime.now()
    date_to = today.strftime("%Y%m%d")
    date_from = (today - timedelta(days=7)).strftime("%Y%m%d")
    try:
        data = _jquants_get("/equities/bars/daily", {
            "code": code, "from": date_from, "to": date_to,
        })
        bars = data.get("data") or data.get("eq_bars_daily") or []
        return {
            "code": code,
            "raw_keys": list(data.keys()),
            "num_bars": len(bars),
            "sample_bar": bars[-1] if bars else None,
            "all_field_names": list(bars[0].keys()) if bars else [],
            "raw_response": data if not bars else None,
        }
    except Exception as e:
        return {"code": code, "error": str(e)}


@app.get("/api/debug/jquants/details/{symbol}")
def debug_jquants_details(symbol: str):
    """Inspect raw /fins/details response for a single stock."""
    code = f"{symbol}0"
    try:
        data = _jquants_get("/fins/details", {"code": code})
        records = data.get("data") or data.get("fs_details") or []
        result = {
            "code": code,
            "raw_keys": list(data.keys()),
            "num_records": len(records),
        }
        if records:
            # Show latest record's structure
            latest = records[0]
            fs = latest.get("FS") or {}
            result["latest_doc_type"] = latest.get("DocType", "")
            result["latest_disc_date"] = latest.get("DiscDate", "")
            result["fs_keys"] = list(fs.keys())[:50]  # first 50 keys
            result["fs_key_count"] = len(fs)
            result["parsed_values"] = _extract_fs_values(fs)
            result["period_type"] = _parse_period_type(latest.get("DocType", ""))
        return result
    except Exception as e:
        return {"code": code, "error": str(e)}


@app.get("/api/debug/jquants/summary/{symbol}")
def debug_jquants_summary(symbol: str):
    """Inspect raw /fins/summary response for a single stock."""
    code = f"{symbol}0"
    try:
        data = _jquants_get("/fins/summary", {"code": code})
        records = data.get("data") or data.get("fs_summary") or []
        records.sort(key=lambda r: r.get("DiscDate", ""), reverse=True)
        result = {
            "code": code,
            "raw_keys": list(data.keys()),
            "num_records": len(records),
        }
        if records:
            latest = records[0]
            result["latest_record"] = latest
            result["all_field_names"] = list(latest.keys())
            # Show forecast-related fields specifically
            forecast_fields = {}
            for k, v in latest.items():
                kl = k.lower()
                if any(x in kl for x in ["eps", "fep", "nxf", "fnp", "roe", "fore", "bps", "div", "payout"]):
                    forecast_fields[k] = v
            result["forecast_related_fields"] = forecast_fields
        return result
    except Exception as e:
        return {"code": code, "error": str(e)}


@app.get("/api/exchange-rate")
def get_exchange_rate():
    return {"usd_jpy_rate": _state["usd_jpy_rate"]}


@app.put("/api/exchange-rate")
def set_exchange_rate(rate: float):
    _state["usd_jpy_rate"] = rate
    _recompute_weights()
    return {"usd_jpy_rate": rate}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_filing_value(raw) -> float | None:
    if pd.isna(raw):
        return None
    if isinstance(raw, str) and "%" in raw:
        try:
            return float(raw.replace("%", "").strip()) / 100.0
        except ValueError:
            return None
    try:
        val = float(raw)
        return val / 100.0 if val > 1.0 else val
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
