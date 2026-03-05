"""FastAPI REST API for Paradaim Portfolio.Tool Trading V2.

Exposes the portfolio management logic as HTTP endpoints for the JavaFX frontend.
"""

from __future__ import annotations

import math
import os
import tempfile
import uuid
from datetime import datetime
from typing import Any

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
    """Refresh prices using yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        raise HTTPException(500, "yfinance not installed")

    portfolio = _state["portfolio"]
    updated = 0

    # Exchange rate
    try:
        ticker = yf.Ticker("USDJPY=X")
        info = ticker.info
        price = info.get("regularMarketPrice")
        if price is not None:
            _state["usd_jpy_rate"] = float(price)
    except Exception:
        pass

    rate = _state["usd_jpy_rate"] or DEFAULT_EXCHANGE_RATE
    adv_updated = 0

    for symbol, position in portfolio.items():
        if position.is_cash:
            continue
        try:
            ticker = yf.Ticker(f"{symbol}.T")

            # Update price from info
            try:
                info = ticker.info or {}
            except Exception:
                info = {}
            price = info.get("regularMarketPrice")
            if price is not None:
                position.price = float(price)
                updated += 1

            # Fetch average volume — try multiple sources
            avg_vol = 0.0
            for vol_key in ("averageDailyVolume3Month", "averageVolume",
                            "averageDailyVolume10Day", "volume"):
                val = info.get(vol_key)
                if val and val > 0:
                    avg_vol = float(val)
                    print(f"  {symbol}: got volume from info[{vol_key}]={avg_vol:.0f}")
                    break

            # Fallback: compute from price history
            if not avg_vol:
                try:
                    hist = ticker.history(period="3mo")
                    if hist is not None and not hist.empty and "Volume" in hist.columns:
                        avg_vol = float(hist["Volume"].mean())
                        print(f"  {symbol}: got volume from 3mo history={avg_vol:.0f}")
                except Exception as hist_err:
                    print(f"  {symbol}: history() failed: {hist_err}")

            if avg_vol > 0 and position.price > 0:
                adv_value_usd = (avg_vol * 0.10 * position.price) / rate
                position.adv_10pct = adv_value_usd
                adv_updated += 1
                print(f"  {symbol}: 10%ADV = {adv_value_usd:,.0f} USD "
                      f"(vol={avg_vol:,.0f} x price={position.price:,.0f} / rate={rate:.2f})")
            else:
                print(f"  {symbol}: WARNING no volume data found (info keys: {list(info.keys())[:10]})")
        except Exception as e:
            print(f"  {symbol}: ERROR {e}")

    # Recompute trading_days for existing proposed executions with updated ADV
    for key, ex in _state["proposed_executions"].items():
        if ex.symbol in portfolio:
            adv = portfolio[ex.symbol].adv_10pct
            if adv > 0:
                ex.trading_days = abs(ex.trade_value_usd) / adv

    _recompute_weights()
    print(f"Price refresh complete: {updated} prices, {adv_updated} ADV values updated")
    return {"message": f"Updated {updated} prices, {adv_updated} ADV values", "usd_jpy_rate": _state["usd_jpy_rate"]}


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
