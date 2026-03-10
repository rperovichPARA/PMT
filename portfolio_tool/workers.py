"""Background QThread workers for network I/O and file parsing."""

from __future__ import annotations

import re
from datetime import datetime

import requests as http_requests

import pandas as pd
from PyQt5.QtCore import QThread, pyqtSignal

from .models import FilingRecord, FundPosition, Position


# ---------------------------------------------------------------------------
# J-Quants V2 API helpers (mirrors api_server.py)
# ---------------------------------------------------------------------------

_JQUANTS_API_KEY = "IsSPKDgnOojzoMEjBGhivJuw7_c9FBPlPDzt4iuYPdc"
_JQUANTS_BASE_URL = "https://api.jquants.com/v2"


def _jquants_get(path: str, params: dict | None = None) -> dict:
    """Make an authenticated GET request to J-Quants V2 API."""
    resp = http_requests.get(
        f"{_JQUANTS_BASE_URL}{path}",
        headers={"x-api-key": _JQUANTS_API_KEY},
        params=params or {},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_usd_jpy_rate() -> float | None:
    """Fetch current USD/JPY rate from a public API."""
    try:
        resp = http_requests.get(
            "https://api.exchangerate-api.com/v4/latest/USD",
            timeout=10,
        )
        resp.raise_for_status()
        rate = resp.json().get("rates", {}).get("JPY")
        if rate and float(rate) > 1.0:
            return float(rate)
    except Exception:
        pass
    return None


def _fetch_jquants_price(symbol: str) -> float:
    """Fetch the latest closing price for a TSE stock from J-Quants."""
    try:
        code = symbol if len(symbol) >= 5 else f"{symbol}0"
        from datetime import timedelta
        end = datetime.now()
        start = end - timedelta(days=10)
        data = _jquants_get("/equities/bars/daily", {
            "code": code,
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
        })
        bars = data.get("daily_quotes", [])
        if bars:
            last_bar = bars[-1]
            price = last_bar.get("Close") or last_bar.get("AdjustmentClose")
            if price is not None:
                return float(price)
    except Exception:
        pass
    return 0.0


# ---------------------------------------------------------------------------
# Exchange-rate worker
# ---------------------------------------------------------------------------

class ExchangeRateWorker(QThread):
    """Fetch USD/JPY from a free FX API in the background."""

    rate_updated = pyqtSignal(float)

    def run(self) -> None:
        rate = _fetch_usd_jpy_rate()
        if rate is not None:
            self.rate_updated.emit(rate)


# ---------------------------------------------------------------------------
# Price-refresh worker
# ---------------------------------------------------------------------------

class PriceRefreshWorker(QThread):
    """Refresh live prices for all non-cash positions via J-Quants."""

    price_updated = pyqtSignal(str, float)
    progress_updated = pyqtSignal(int, str)
    completed = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, portfolio: dict[str, Position], parent=None) -> None:
        super().__init__(parent)
        self.portfolio = portfolio

    def run(self) -> None:
        try:
            count = 0
            total = len(self.portfolio)
            # Exchange rate first
            self.progress_updated.emit(0, "Fetching USD/JPY exchange rate...")
            rate = _fetch_usd_jpy_rate()
            if rate is not None:
                self.price_updated.emit("USD/JPY", rate)

            for symbol, position in self.portfolio.items():
                if symbol == "JPY":
                    count += 1
                    self.progress_updated.emit(
                        int(count / max(total, 1) * 100),
                        f"Skipping cash position {symbol}...",
                    )
                    continue
                if not position.is_cash:
                    self.progress_updated.emit(
                        int(count / max(total, 1) * 100),
                        f"Fetching price for {symbol} ({count + 1}/{total})...",
                    )
                    price = _fetch_jquants_price(symbol)
                    if price > 0:
                        self.price_updated.emit(symbol, price)
                count += 1

            self.progress_updated.emit(100, "Price refresh complete")
            self.completed.emit()
        except Exception as exc:
            self.error.emit(f"Error refreshing prices: {exc}")


# ---------------------------------------------------------------------------
# Portfolio-import worker
# ---------------------------------------------------------------------------

class PortfolioImportWorker(QThread):
    """Parse a portfolio Excel file in the background."""

    progress_updated = pyqtSignal(int, str)
    import_completed = pyqtSignal(dict, list, float)  # portfolio, fund_names, usd_jpy_rate
    import_error = pyqtSignal(str)

    def __init__(self, file_path: str, parent=None) -> None:
        super().__init__(parent)
        self.file_path = file_path

    def run(self) -> None:
        try:
            portfolio: dict[str, Position] = {}
            usd_jpy_rate = 0.0

            self.progress_updated.emit(10, "Reading Excel file...")
            df = pd.read_excel(self.file_path)
            self.progress_updated.emit(30, "Analyzing data...")

            for col in ("Symbol", "Name", "Quantity"):
                if col not in df.columns:
                    self.import_error.emit(f"Required column '{col}' not found")
                    return

            has_fund = "Fund" in df.columns
            has_adv = "10% 3m ADV" in df.columns
            has_price = "Price" in df.columns
            has_os = "OS" in df.columns
            has_pct = "% of Company" in df.columns

            if not has_price:
                self.import_error.emit(
                    "Price column not found in Excel file"
                )
                return

            fund_names = (
                df["Fund"].dropna().unique().tolist() if has_fund else ["Default"]
            )
            total_rows = len(df)

            for i, row in df.iterrows():
                symbol = str(row["Symbol"]).strip()
                name = str(row["Name"]).strip()
                quantity = float(row["Quantity"])
                fund = str(row["Fund"]).strip() if has_fund else "Default"

                adv_10pct = (
                    float(row["10% 3m ADV"])
                    if has_adv and not pd.isna(row["10% 3m ADV"])
                    else 0.0
                )
                os_shares = (
                    float(row["OS"])
                    if has_os and not pd.isna(row["OS"])
                    else 0.0
                )
                pct_of_company = 0.0
                if has_pct and not pd.isna(row["% of Company"]):
                    pct_of_company = float(row["% of Company"])
                elif os_shares > 0 and quantity > 0:
                    pct_of_company = quantity / os_shares

                self.progress_updated.emit(
                    30 + int(65 * i / max(total_rows, 1)),
                    f"Processing {symbol} for fund {fund}...",
                )

                if not symbol or pd.isna(symbol):
                    continue

                is_cash = symbol.upper() in ("JPY", "USD")
                currency = symbol.upper() if is_cash else "JPY"

                # Determine price
                price = 0.0
                if has_price and not pd.isna(row["Price"]):
                    price = float(row["Price"])
                    if symbol.upper() == "JPY" and is_cash and price > 1.0:
                        usd_jpy_rate = price
                elif is_cash:
                    price = 1.0

                if symbol not in portfolio:
                    portfolio[symbol] = Position(
                        symbol=symbol,
                        name=name,
                        price=price,
                        is_cash=is_cash,
                        adv_10pct=adv_10pct,
                        currency=currency,
                        os_shares=os_shares,
                    )

                portfolio[symbol].funds[fund] = FundPosition(
                    quantity=quantity,
                    pct_of_company=pct_of_company,
                )

            self.progress_updated.emit(100, "Import complete")
            self.import_completed.emit(portfolio, fund_names, usd_jpy_rate)

        except Exception as exc:
            self.import_error.emit(f"Error importing portfolio: {exc}")



# ---------------------------------------------------------------------------
# Trades-import worker
# ---------------------------------------------------------------------------

class TradesImportWorker(QThread):
    """Parse an open-orders Excel file with per-fund sections."""

    progress_updated = pyqtSignal(int, str)
    import_completed = pyqtSignal(list)
    import_error = pyqtSignal(str)

    def __init__(self, file_path: str, parent=None) -> None:
        super().__init__(parent)
        self.file_path = file_path

    def run(self) -> None:
        try:
            trades: list[dict] = []
            self.progress_updated.emit(10, "Reading Excel file...")

            df = self._read_excel()
            if df is None:
                return

            self.progress_updated.emit(30, "Analyzing data...")

            current_fund = None
            processing_data = False
            column_indices = None
            total_rows = len(df)

            for i, row in df.iterrows():
                if row.isna().all():
                    continue

                first_cell = row.iloc[0]

                # Section header
                if isinstance(first_cell, str) and "Fund Open Orders" in first_cell:
                    fund_match = re.match(
                        r"^(.*?)\s+Fund\s+Open\s+Orders", first_cell
                    )
                    if fund_match:
                        current_fund = fund_match.group(1).strip()
                        processing_data = False
                        if current_fund == "Aggregate":
                            current_fund = None
                    self.progress_updated.emit(
                        30 + int(20 * i / max(total_rows, 1)),
                        f"Found section: {current_fund}",
                    )
                    continue

                # Column header row
                if (
                    current_fund
                    and not processing_data
                    and isinstance(first_cell, str)
                    and first_cell == "Side"
                ):
                    column_indices = self._parse_header_row(row)
                    if column_indices:
                        processing_data = True
                    continue

                # Data rows
                if processing_data and current_fund and column_indices:
                    trade = self._parse_data_row(
                        row, column_indices, current_fund
                    )
                    if trade:
                        trades.append(trade)
                    self.progress_updated.emit(
                        50 + int(40 * i / max(total_rows, 1)),
                        f"Processing trades for {current_fund}...",
                    )

            self.progress_updated.emit(100, "Import complete")
            self.import_completed.emit(trades)

        except Exception as exc:
            self.import_error.emit(f"Error importing trades: {exc}")

    def _read_excel(self) -> pd.DataFrame | None:
        """Try multiple backends to read the Excel file."""
        try:
            return pd.read_excel(self.file_path, header=None)
        except Exception as first_err:
            if self.file_path.lower().endswith(".xlsx"):
                try:
                    import openpyxl

                    wb = openpyxl.load_workbook(self.file_path)
                    sheet = wb.active
                    data = [[cell.value for cell in r] for r in sheet.rows]
                    return pd.DataFrame(data)
                except ImportError:
                    self.import_error.emit(
                        "Required Excel libraries not found.\n"
                        "pip install xlrd openpyxl"
                    )
                    return None
                except Exception as exc:
                    self.import_error.emit(f"Error reading Excel file: {exc}")
                    return None
            else:
                self.import_error.emit(f"Error reading Excel file: {first_err}")
                return None

    @staticmethod
    def _parse_header_row(row) -> dict | None:
        mapping = {"side": None, "ticker": None, "limit_px": None, "shares": None}
        col_map = {
            "Side": "side",
            "Ticker": "ticker",
            "Limit PX": "limit_px",
            "Shares to Trade": "shares",
        }
        for j, cell in enumerate(row):
            if cell in col_map:
                mapping[col_map[cell]] = j
        return mapping if all(v is not None for v in mapping.values()) else None

    @staticmethod
    def _parse_data_row(row, col_idx: dict, fund: str) -> dict | None:
        side_val = row.iloc[col_idx["side"]]
        if not isinstance(side_val, str):
            return None
        side = side_val.strip()
        if side == "Hold":
            return None

        ticker_val = row.iloc[col_idx["ticker"]]
        ticker = (
            str(ticker_val).strip()
            if ticker_val is not None and not pd.isna(ticker_val)
            else ""
        )
        if not ticker:
            return None

        limit_px = row.iloc[col_idx["limit_px"]]
        limit_px = 0 if pd.isna(limit_px) else limit_px

        shares = row.iloc[col_idx["shares"]]
        shares = 0 if pd.isna(shares) else shares
        if shares == 0:
            return None

        return {
            "fund": fund,
            "side": side,
            "ticker": ticker,
            "limit_px": limit_px,
            "shares": shares,
        }


# ---------------------------------------------------------------------------
# Filings-import worker
# ---------------------------------------------------------------------------

class FilingsImportWorker(QThread):
    """Parse a filings Excel file."""

    progress_updated = pyqtSignal(int, str)
    import_completed = pyqtSignal(dict)
    import_error = pyqtSignal(str)

    def __init__(self, file_path: str, parent=None) -> None:
        super().__init__(parent)
        self.file_path = file_path

    def run(self) -> None:
        try:
            filings: dict[str, FilingRecord] = {}
            self.progress_updated.emit(10, "Reading Excel file...")
            df = pd.read_excel(self.file_path)
            self.progress_updated.emit(30, "Analyzing data...")

            for col in ("Symbol", "Name", "Last Filing", "Date"):
                if col not in df.columns:
                    self.import_error.emit(f"Required column '{col}' not found")
                    return

            total_rows = len(df)

            for i, row in df.iterrows():
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

                last_filing = self._parse_filing_value(row["Last Filing"])

                self.progress_updated.emit(
                    30 + int(65 * i / max(total_rows, 1)),
                    f"Processing {symbol}...",
                )

                filings[symbol] = FilingRecord(
                    name=name, date=date, last_filing=last_filing
                )

            self.progress_updated.emit(100, "Import complete")
            self.import_completed.emit(filings)

        except Exception as exc:
            self.import_error.emit(f"Error importing filings: {exc}")

    @staticmethod
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
