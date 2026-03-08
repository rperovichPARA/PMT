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
    "metrics": {},             # dict[str, dict] – per-symbol metrics from /fins/statements
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
            funds=funds_out,
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

            if symbol not in portfolio:
                portfolio[symbol] = Position(
                    symbol=symbol, name=name, price=price,
                    is_cash=is_cash, adv_10pct=adv,
                    currency=currency, os_shares=os_shares,
                )
            portfolio[symbol].funds[fund] = FundPosition(
                quantity=quantity, pct_of_company=pct,
            )

        _state["portfolio"] = portfolio
        _state["fund_names"] = fund_names
        _state["usd_jpy_rate"] = usd_jpy_rate
        _state["proposed_executions"] = {}
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

    for fn, qty in req.fund_quantities.items():
        pos.funds[fn] = FundPosition(quantity=qty)
        if fn not in fund_names:
            fund_names.append(fn)

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
        result.append(ExecutionOut(
            key=key,
            fund=ex.fund,
            symbol=ex.symbol,
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

    # Fetch all symbols in parallel
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
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
    """Refresh fundamental metrics using J-Quants V2 /fins/statements and /indices/bars/daily/topix."""
    import numpy as np

    portfolio = _state["portfolio"]
    symbols = [s for s, p in portfolio.items() if not p.is_cash]
    updated = 0
    errors = []

    today = datetime.now()
    date_to = today.strftime("%Y%m%d")
    # ~3 years of data for CAGR and beta calculations
    date_from_3y = (today - timedelta(days=3 * 365)).strftime("%Y%m%d")
    # 1 year for beta
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

    # ---- Parallel fetch: statements + stock bars for all symbols ----
    def _fetch_symbol_data(symbol: str) -> dict:
        code = f"{symbol}0"
        stmt_data = _jquants_get("/fins/statements", {"code": code})
        stock_data = _jquants_get("/equities/bars/daily", {
            "code": code,
            "from": date_from_1y,
            "to": date_to,
        })
        return {"symbol": symbol, "stmt_data": stmt_data, "stock_data": stock_data}

    prefetched: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_symbol_data, s): s for s in symbols}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                prefetched[sym] = future.result()
            except Exception as e:
                print(f"  {sym}: ERROR fetching data: {e}")
                errors.append(f"{sym}: {e}")

    # Helper to safely parse string -> float
    def _pf(val) -> float | None:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    for symbol in symbols:
        if symbol not in prefetched:
            continue
        position = portfolio[symbol]
        fetched = prefetched[symbol]
        m: dict[str, Any] = {}

        try:
            # ---- Fetch financial summary (Standard plan endpoint) ----
            stmt_data = _jquants_get("/fins/summary", {"code": code})
            stmts = stmt_data.get("data") or stmt_data.get("statements") or []
            if not stmts:
                print(f"  {symbol}: no statements data")
                errors.append(f"{symbol}: no statements")
                continue

            # Sort by disclosed date descending to get most recent first
            stmts.sort(key=lambda s: s.get("DiscDate", ""), reverse=True)

            # Get the latest annual/full-year statement for result data
            # CurPerType: "FY" = full year, "3Q", "2Q", "1Q"
            latest_stmt = stmts[0]  # most recent disclosure

            # Find latest FY statement for result metrics
            fy_stmt = None
            for s in stmts:
                if s.get("CurPerType") == "FY":
                    fy_stmt = s
                    break

            # Use latest statement that has forecast data
            forecast_stmt = None
            for s in stmts:
                if _pf(s.get("FEPS")) is not None:
                    forecast_stmt = s
                    break

            price = position.price

            # ---- BPS (BookValuePerShare) -> PBR ----
            bvps = None
            for s in stmts:
                bvps = _pf(s.get("BPS"))
                if bvps is not None:
                    break
            if bvps and bvps > 0 and price > 0:
                m["pbr"] = round(price / bvps, 2)

            # ---- PE LTM: trailing 4 quarters of EPS ----
            # Collect quarterly EPS values (most recent 4 quarters)
            quarterly_eps = []
            seen_periods = set()
            for s in stmts:
                period_end = s.get("CurPerEn", "")
                period_type = s.get("CurPerType", "")
                if period_end in seen_periods:
                    continue
                eps_val = _pf(s.get("EPS"))
                if eps_val is not None and period_type in ("1Q", "2Q", "3Q", "FY"):
                    quarterly_eps.append({"type": period_type, "eps": eps_val,
                                          "end": period_end})
                    seen_periods.add(period_end)
                if len(quarterly_eps) >= 8:
                    break

            # For LTM EPS, take the most recent FY EPS or sum approach
            # Simplest: if we have FY, use it. Otherwise cumulate.
            ltm_eps = None
            if fy_stmt:
                ltm_eps = _pf(fy_stmt.get("EPS"))
            if ltm_eps and ltm_eps > 0 and price > 0:
                m["pe_ltm"] = round(price / ltm_eps, 1)

            # ---- PE NTM: FEPS (ForecastEarningsPerShare, current year) ----
            forecast_eps = None
            if forecast_stmt:
                forecast_eps = _pf(forecast_stmt.get("FEPS"))
            if forecast_eps and forecast_eps > 0 and price > 0:
                m["pe_ntm"] = round(price / forecast_eps, 1)

            # ---- PE 24M: Next-year forecast EPS ----
            # Try NxFEPS (full-year), NxFEPS2Q (2Q), or derive from NxFNp / shares
            next_yr_eps = None
            for s in stmts:
                next_yr_eps = _pf(s.get("NxFEPS")) or _pf(s.get("NxFEPS2Q"))
                if next_yr_eps is not None:
                    break
            if next_yr_eps is None:
                # Derive from NxFNp (next-year forecast net profit) / outstanding shares
                for s in stmts:
                    nyf_profit = _pf(s.get("NxFNp"))
                    if nyf_profit is not None and position.os_shares > 0:
                        next_yr_eps = nyf_profit / position.os_shares
                        break
            if next_yr_eps and next_yr_eps > 0 and price > 0:
                m["pe_24m"] = round(price / next_yr_eps, 1)

            # ---- PEGc: PE NTM / EPS growth rate (historical) ----
            # Compute EPS CAGR from historical data for PEGc
            historical_eps = _collect_annual_values(stmts, "EPS", _pf)
            eps_growth = _compute_cagr(historical_eps)
            if m.get("pe_ntm") and eps_growth and eps_growth > 0:
                m["peg_c"] = round(m["pe_ntm"] / (eps_growth * 100), 2)

            # ---- PEG n: PE 24M / next year EPS growth ----
            if m.get("pe_24m") and forecast_eps and next_yr_eps and forecast_eps > 0:
                next_yr_growth = (next_yr_eps - forecast_eps) / abs(forecast_eps)
                if next_yr_growth > 0:
                    m["peg_n"] = round(m["pe_24m"] / (next_yr_growth * 100), 2)

            # ---- ROE (l): NP (Net Profit) / Eq (Equity) ----
            profit = None
            equity = None
            for s in stmts:
                if profit is None:
                    profit = _pf(s.get("NP"))
                if equity is None:
                    equity = _pf(s.get("Eq"))
                if profit is not None and equity is not None:
                    break
            if profit is not None and equity and equity > 0:
                m["roe_l"] = round(profit / equity * 100, 1)

            # ---- ROE NTM: FNP (Forecast Net Profit) / Equity ----
            forecast_profit = None
            if forecast_stmt:
                forecast_profit = _pf(forecast_stmt.get("FNP"))
            if forecast_profit is not None and equity and equity > 0:
                m["roe_ntm"] = round(forecast_profit / equity * 100, 1)

            # ---- Plowback: 1 - PayoutRatioAnn ----
            payout = None
            for s in stmts:
                payout = _pf(s.get("PayoutRatioAnn"))
                if payout is not None:
                    break
            if payout is not None:
                # J-Quants returns payout as percentage (e.g. 30.5 for 30.5%)
                payout_dec = payout / 100.0 if payout > 1.0 else payout
                m["plowback"] = round(1.0 - payout_dec, 3)
                m["payout_ratio"] = round(payout_dec * 100, 1)

            # ---- Div Yield: DivAnn (actual) or FDivAnn (forecast) / Price ----
            div_annual = None
            for s in stmts:
                div_annual = _pf(s.get("DivAnn")) or _pf(s.get("FDivAnn"))
                if div_annual is not None:
                    break
            if div_annual is not None and price > 0:
                m["div_yield"] = round(div_annual / price * 100, 2)

            # ---- OPM: OP (Operating Profit) / Sales ----
            op_profit = None
            net_sales = None
            for s in stmts:
                if op_profit is None:
                    op_profit = _pf(s.get("OP"))
                if net_sales is None:
                    net_sales = _pf(s.get("Sales"))
                if op_profit is not None and net_sales is not None:
                    break
            if op_profit is not None and net_sales and net_sales > 0:
                m["opm"] = round(op_profit / net_sales * 100, 1)

            # ---- 2Y Sales CAGR ----
            historical_sales = _collect_annual_values(stmts, "Sales", _pf)
            sales_cagr = _compute_cagr(historical_sales)
            if sales_cagr is not None:
                m["sales_cagr_2y"] = round(sales_cagr * 100, 1)

            # ---- 2Y Op CAGR ----
            historical_op = _collect_annual_values(stmts, "OP", _pf)
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
                        # Build date->close map for the stock
                        stock_closes_by_date: dict[str, float] = {}
                        for bar in stock_bars:
                            dt = bar.get("Date", "")
                            c = bar.get("Close") or bar.get("AdjClose") or bar.get("C") or bar.get("AdjC")
                            if c is not None and dt:
                                try:
                                    stock_closes_by_date[dt] = float(c)
                                except (ValueError, TypeError):
                                    pass

                        # Align on common dates (reuse cached TOPIX data)
                        common_dates = sorted(set(stock_closes_by_date.keys()) & set(topix_closes_by_date.keys()))
                        if len(common_dates) >= 30:
                            s_prices = np.array([stock_closes_by_date[d] for d in common_dates])
                            t_prices = np.array([topix_closes_by_date[d] for d in common_dates])
                            s_ret = (s_prices[1:] - s_prices[:-1]) / s_prices[:-1]
                            t_ret = (t_prices[1:] - t_prices[:-1]) / t_prices[:-1]
                            # Beta = Cov(stock, market) / Var(market)
                            cov = np.cov(s_ret, t_ret)
                            if cov[1, 1] > 0:
                                beta_val = cov[0, 1] / cov[1, 1]
                                m["beta"] = round(float(beta_val), 2)
                except Exception as e:
                    print(f"  {symbol}: beta calc error: {e}")

            _state["metrics"][symbol] = m
            updated += 1
            print(f"  {symbol}: {len(m)} metrics computed")

        except Exception as e:
            print(f"  {symbol}: ERROR {e}")
            errors.append(f"{symbol}: {e}")

    _recompute_weights()
    msg = f"Updated metrics for {updated} positions (J-Quants V2)"
    if errors:
        msg += f" | {len(errors)} errors"
    print(f"Metrics refresh complete: {msg}")
    return {"message": msg, "errors": errors}


def _collect_annual_values(
    stmts: list[dict], field: str, parse_fn
) -> list[tuple[str, float]]:
    """Collect (fiscal_year_end, value) pairs from FY statements for CAGR calculation."""
    values = []
    seen_years = set()
    for s in stmts:
        if s.get("CurPerType") != "FY":
            continue
        fy_end = s.get("CurFYEn", "")
        if fy_end in seen_years:
            continue
        val = parse_fn(s.get(field))
        if val is not None and val > 0:
            values.append((fy_end, val))
            seen_years.add(fy_end)
    # Sort oldest first
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
