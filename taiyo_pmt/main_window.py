"""Main application window for Taiyo PMT Trading V2."""

from __future__ import annotations

import math
import os
from datetime import datetime

import pandas as pd
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QGridLayout,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .charts import build_cash_path_chart
from .dialogs import AddPositionDialog, TargetPriceDialog, TradeDialog
from .models import (
    BUY_COLOR_RGB,
    CASH_SYMBOLS,
    DEFAULT_EXCHANGE_RATE,
    FIXED_COLUMNS,
    FUND_COLORS_RGB,
    FUND_COLUMNS,
    NUM_FIXED_COLUMNS,
    NUM_FUND_COLUMNS,
    SELL_COLOR_RGB,
    FundPosition,
    Position,
    ProposedExecution,
    calculate_target_raw_from_shares,
    calculate_value_usd,
    fund_column_index,
    normalize_symbol,
)
from .workers import (
    ExchangeRateWorker,
    FilingsImportWorker,
    PortfolioImportWorker,
    PriceRefreshWorker,
    TradesImportWorker,
)


def _qcolor(rgb: tuple[int, int, int]) -> QColor:
    return QColor(*rgb)


class PortfolioManager(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Taiyo PMT Trading V2")
        self.resize(1400, 700)

        # Core state
        self.portfolio: dict[str, Position] = {}
        self.usd_jpy_rate: float = 0.0
        self.fund_names: list[str] = []
        self.filings: dict = {}
        self.proposed_executions: dict[str, ProposedExecution] = {}

        # UI flags
        self.filings_visible = False
        self.chart_visible = False
        self.use_yfinance_pricing = False
        self.auto_sort_enabled = True

        # Sort state
        self._sort_column: int | None = None
        self._sort_reverse = False

        self._build_ui()
        self._update_exchange_rate()

    # =====================================================================
    #  UI CONSTRUCTION
    # =====================================================================

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        self._build_menu_bar()

        self._main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self._main_splitter)

        # Left panel
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self._build_portfolio_frame(left_layout)
        self._build_position_frame(left_layout)
        self._main_splitter.addWidget(left)

        # Middle panel (filings - hidden initially)
        self._middle_panel = QWidget()
        mid_layout = QVBoxLayout(self._middle_panel)
        self._build_filings_frame(mid_layout)
        self._middle_panel.setVisible(False)
        self._main_splitter.addWidget(self._middle_panel)

        # Right panel
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self._build_proposed_trades_frame(right_layout)
        self._main_splitter.addWidget(right)

        self._main_splitter.setSizes([1050, 0, 350])

    def _build_menu_bar(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("File")
        file_menu.addAction("Import Portfolio", self._import_portfolio)
        file_menu.addAction("Export Proposed Trades", self._export_proposed_trades)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        settings = mb.addMenu("Settings")
        price_menu = settings.addMenu("Price Source")

        self._excel_price_action = price_menu.addAction("Use Excel Prices")
        self._excel_price_action.setCheckable(True)
        self._excel_price_action.setChecked(True)
        self._excel_price_action.triggered.connect(self._set_excel_prices)

        self._yfinance_price_action = price_menu.addAction("Use YFinance Prices")
        self._yfinance_price_action.setCheckable(True)
        self._yfinance_price_action.triggered.connect(self._set_yfinance_prices)

    def _set_excel_prices(self) -> None:
        if not self._excel_price_action.isChecked():
            self._excel_price_action.setChecked(True)
            return
        self.use_yfinance_pricing = False
        self._yfinance_price_action.setChecked(False)
        QMessageBox.information(self, "Price Source", "Using prices from Excel file")

    def _set_yfinance_prices(self) -> None:
        if not self._yfinance_price_action.isChecked():
            self._yfinance_price_action.setChecked(True)
            return
        self.use_yfinance_pricing = True
        self._excel_price_action.setChecked(False)
        reply = QMessageBox.question(
            self,
            "Refresh Prices",
            "Do you want to refresh all prices from YFinance now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._refresh_prices()

    # ---- portfolio frame ---------------------------------------------------

    def _build_portfolio_frame(self, parent_layout) -> None:
        group = QGroupBox("Portfolio")
        self._portfolio_group = group
        layout = QVBoxLayout(group)

        top = QHBoxLayout()
        top.addWidget(self._btn("Import Portfolio", self._import_portfolio))
        top.addWidget(self._btn("Import Trades", self._import_trades))
        top.addWidget(self._btn("Import Filings", self._import_filings))

        self._show_filings_btn = self._btn("Show Filings", self._toggle_filings)
        top.addWidget(self._show_filings_btn)
        top.addStretch()
        top.addWidget(self._btn("Create Trade", self._open_trade_dialog))
        layout.addLayout(top)

        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        self._header_table = QTableWidget(1, 0)
        self._header_table.setMaximumHeight(25)
        self._header_table.horizontalHeader().setVisible(False)
        self._header_table.verticalHeader().setVisible(False)
        self._header_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._header_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._portfolio_table = QTableWidget()
        self._portfolio_table.setAlternatingRowColors(True)
        self._portfolio_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._portfolio_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._portfolio_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        self._portfolio_table.horizontalHeader().setStretchLastSection(False)
        self._portfolio_table.verticalHeader().setVisible(False)
        self._portfolio_table.setStyleSheet(
            "QTableWidget::item { border-right: 0px; padding: 6px; }"
            "QHeaderView::section { border-right: 0px; }"
        )
        self._portfolio_table.itemSelectionChanged.connect(self._on_position_select)
        self._portfolio_table.cellDoubleClicked.connect(self._on_portfolio_dbl_click)
        self._portfolio_table.horizontalHeader().sectionClicked.connect(
            self._sort_portfolio_table
        )
        self._portfolio_table.horizontalScrollBar().valueChanged.connect(
            self._header_table.horizontalScrollBar().setValue
        )

        cl.addWidget(self._header_table)
        cl.addWidget(self._portfolio_table)
        layout.addWidget(container)

        bottom = QHBoxLayout()
        bottom.addWidget(self._btn("Add Position", self._add_position_dialog))
        bottom.addWidget(self._btn("Remove Position", self._remove_position))
        bottom.addWidget(self._btn("Refresh Prices", self._refresh_prices))
        bottom.addWidget(
            self._btn("Clear All Proposed Trades", self._clear_proposed_executions)
        )
        bottom.addStretch()
        self._exchange_rate_label = QLabel("USD/JPY: Loading...")
        bottom.addWidget(self._exchange_rate_label)
        layout.addLayout(bottom)

        parent_layout.addWidget(group)

    # ---- filings frame -----------------------------------------------------

    def _build_filings_frame(self, parent_layout) -> None:
        group = QGroupBox("Filings Information")
        layout = QVBoxLayout(group)

        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(self._btn("Hide Filings", self._toggle_filings))
        layout.addLayout(top)

        self._filings_table = QTableWidget()
        self._filings_table.setAlternatingRowColors(True)
        self._filings_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._filings_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._filings_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        self._filings_table.horizontalHeader().setStretchLastSection(False)
        self._filings_table.verticalHeader().setVisible(False)
        cols = [
            "Symbol", "Name", "Date", "Last Filing",
            "% to Next Upward", "% to Next Downward",
        ]
        self._filings_table.setColumnCount(len(cols))
        self._filings_table.setHorizontalHeaderLabels(cols)
        for i, w in enumerate([80, 150, 100, 100, 130, 130]):
            self._filings_table.setColumnWidth(i, w)
        self._filings_table.setStyleSheet(
            "QTableWidget::item { border-right: 0px; padding: 6px; }"
            "QHeaderView::section { border-right: 0px; }"
        )
        self._filings_table.horizontalHeader().sectionClicked.connect(
            self._sort_filings_table
        )
        layout.addWidget(self._filings_table)
        parent_layout.addWidget(group)

    # ---- position-details frame --------------------------------------------

    def _build_position_frame(self, parent_layout) -> None:
        group = QGroupBox("Position Details")
        gl = QGridLayout(group)

        self._pos_labels: dict[str, QLabel] = {}
        fields = [
            ("Symbol:", 0, 0), ("Name:", 0, 2),
            ("Price (JPY):", 1, 0), ("Quantity:", 1, 2),
            ("Value (JPY):", 2, 0), ("Value (USD):", 2, 2),
            ("Weight:", 3, 0), ("Current Rel. Weight:", 3, 2),
        ]
        for label_text, r, c in fields:
            gl.addWidget(QLabel(label_text), r, c)
            val = QLabel("")
            gl.addWidget(val, r, c + 1)
            self._pos_labels[label_text] = val

        parent_layout.addWidget(group)

    # ---- proposed-trades frame ---------------------------------------------

    def _build_proposed_trades_frame(self, parent_layout) -> None:
        self._right_splitter = QSplitter(Qt.Vertical)

        trades_group = QGroupBox("Proposed Trades")
        tl = QVBoxLayout(trades_group)

        top = QHBoxLayout()
        self._total_usd_label = QLabel("Net Total: $0.00")
        top.addWidget(self._total_usd_label)
        top.addStretch()
        self._cash_path_btn = QPushButton("Show Cash Path")
        self._cash_path_btn.clicked.connect(self._toggle_cash_path)
        top.addWidget(self._cash_path_btn)
        tl.addLayout(top)

        self._proposed_table = QTableWidget()
        self._proposed_table.setAlternatingRowColors(True)
        self._proposed_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._proposed_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._proposed_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        self._proposed_table.horizontalHeader().setStretchLastSection(False)
        cols = [
            "Trade Type", "Ticker", "Name", "Shares", "USD Value",
            "Trading Days", "Avg Rel Weight", "Target Price", "% to Curr Price",
        ]
        self._proposed_table.setColumnCount(len(cols))
        self._proposed_table.setHorizontalHeaderLabels(cols)
        for i, w in enumerate([80, 80, 150, 90, 90, 90, 90, 100, 100]):
            self._proposed_table.setColumnWidth(i, w)

        self._proposed_table.cellDoubleClicked.connect(
            self._on_proposed_trade_dbl_click
        )
        self._proposed_table.itemSelectionChanged.connect(
            self._on_proposed_trade_select
        )
        tl.addWidget(self._proposed_table)

        btns = QHBoxLayout()
        self._edit_trade_btn = self._btn("Edit Selected Trade", self._edit_proposed_trade)
        self._edit_trade_btn.setEnabled(False)
        btns.addWidget(self._edit_trade_btn)

        self._delete_trade_btn = self._btn(
            "Delete Selected Trade", self._delete_proposed_trade
        )
        self._delete_trade_btn.setEnabled(False)
        btns.addWidget(self._delete_trade_btn)
        btns.addWidget(self._btn("Clear All Trades", self._clear_proposed_executions))
        btns.addWidget(self._btn("Export Trades", self._export_proposed_trades))
        tl.addLayout(btns)

        self._right_splitter.addWidget(trades_group)

        self._chart_frame = QWidget()
        self._chart_layout = QVBoxLayout(self._chart_frame)
        self._chart_frame.setVisible(False)
        self._right_splitter.addWidget(self._chart_frame)
        self._right_splitter.setSizes([350, 0])

        parent_layout.addWidget(self._right_splitter)

    # ---- helper ------------------------------------------------------------

    @staticmethod
    def _btn(text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(slot)
        return b

    # =====================================================================
    #  EXCHANGE RATE
    # =====================================================================

    def _update_exchange_rate(self) -> None:
        jpy = self.portfolio.get("JPY")
        if jpy and jpy.is_cash and jpy.price > 1.0:
            self.usd_jpy_rate = jpy.price
            self._exchange_rate_label.setText(f"USD/JPY: {self.usd_jpy_rate:.2f}")
            return

        self._fx_worker = ExchangeRateWorker()
        self._fx_worker.rate_updated.connect(self._on_exchange_rate)
        self._fx_worker.start()

    def _on_exchange_rate(self, rate: float) -> None:
        self.usd_jpy_rate = rate
        self._exchange_rate_label.setText(f"USD/JPY: {rate:.2f}")
        usd = self.portfolio.get("USD")
        if usd and usd.is_cash:
            usd.price = rate

    # =====================================================================
    #  IMPORT PORTFOLIO
    # =====================================================================

    def _import_portfolio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel File", "", "Excel files (*.xlsx);;All files (*.*)"
        )
        if not path:
            return

        progress = self._make_progress("Importing portfolio data...", 100)

        self._import_worker = PortfolioImportWorker(path, self.use_yfinance_pricing)
        self._import_worker.progress_updated.connect(
            lambda v, s: self._update_progress(progress, v, s)
        )
        self._import_worker.import_completed.connect(self._on_portfolio_imported)
        self._import_worker.import_error.connect(
            lambda msg: self._on_import_error(progress, msg)
        )
        self._import_worker.start()

    def _on_portfolio_imported(self, portfolio, fund_names, usd_jpy_rate) -> None:
        self.portfolio = portfolio
        self.fund_names = fund_names

        jpy = portfolio.get("JPY")
        if jpy and jpy.is_cash and jpy.price > 1.0:
            self.usd_jpy_rate = jpy.price
            self._exchange_rate_label.setText(f"USD/JPY: {self.usd_jpy_rate:.2f}")
            usd = portfolio.get("USD")
            if usd:
                usd.price = self.usd_jpy_rate
        elif usd_jpy_rate > 0:
            self.usd_jpy_rate = usd_jpy_rate
            self._exchange_rate_label.setText(f"USD/JPY: {usd_jpy_rate:.2f}")

        if self.usd_jpy_rate <= 1.0:
            self.usd_jpy_rate = DEFAULT_EXCHANGE_RATE
            self._exchange_rate_label.setText(
                f"USD/JPY: {self.usd_jpy_rate:.2f} (default)"
            )

        self._refresh_portfolio_display()

        if self.fund_names:
            self._sort_column = fund_column_index(0, 0)
            self._sort_reverse = False
            self._sort_portfolio_table(self._sort_column)

    # =====================================================================
    #  IMPORT TRADES
    # =====================================================================

    def _import_trades(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Open Orders Excel File",
            "",
            "Excel files (*.xls *.xlsx);;All files (*.*)",
        )
        if not path:
            return

        progress = self._make_progress("Importing trades data...", 100)
        self._trades_worker = TradesImportWorker(path)
        self._trades_worker.progress_updated.connect(
            lambda v, s: self._update_progress(progress, v, s)
        )
        self._trades_worker.import_completed.connect(self._on_trades_imported)
        self._trades_worker.import_error.connect(
            lambda msg: self._on_import_error(progress, msg)
        )
        self._trades_worker.start()

    def _on_trades_imported(self, trades: list[dict]) -> None:
        prev_sort = self.auto_sort_enabled
        self.auto_sort_enabled = False

        if not trades:
            QMessageBox.information(self, "Import Complete", "No valid trades found.")
            self.auto_sort_enabled = prev_sort
            return
        if not self.portfolio:
            QMessageBox.warning(
                self, "Warning", "Please import a portfolio first."
            )
            self.auto_sort_enabled = prev_sort
            return

        progress = self._make_progress(
            "Converting trades...", len(trades)
        )
        ok = skipped = 0
        symbols_done: set[str] = set()

        for i, trade in enumerate(trades):
            progress.setValue(i)
            QApplication.processEvents()
            if progress.wasCanceled():
                break

            fund_name = trade.get("fund", "")
            raw_ticker = trade.get("ticker", "")
            symbol = normalize_symbol(raw_ticker)
            side = str(trade.get("side", "")).strip()

            if not fund_name or not symbol or not side:
                skipped += 1
                continue

            try:
                shares = float(trade.get("shares", 0))
                if shares == 0:
                    raise ValueError
            except (ValueError, TypeError):
                skipped += 1
                continue

            try:
                limit_px = float(trade.get("limit_px", 0))
            except (ValueError, TypeError):
                limit_px = 0.0

            # Match symbol in portfolio
            matched = None
            for candidate in (symbol, f"{symbol} JP"):
                if candidate in self.portfolio:
                    matched = candidate
                    break
            if not matched or fund_name not in self.fund_names:
                skipped += 1
                continue

            pos = self.portfolio[matched]
            if fund_name not in pos.funds:
                skipped += 1
                continue

            price = pos.price if limit_px == 0 else limit_px
            if price <= 0:
                skipped += 1
                continue

            current_qty = pos.funds[fund_name].quantity
            target_raw = calculate_target_raw_from_shares(
                self.portfolio, fund_name, matched, current_qty, shares, side
            )
            if target_raw is None:
                skipped += 1
                continue

            trade_qty = abs(shares)
            if side.startswith("Sell"):
                trade_qty = -trade_qty

            trade_val_jpy = abs(shares * price)
            rate = self.usd_jpy_rate if self.usd_jpy_rate > 0 else DEFAULT_EXCHANGE_RATE
            trade_val_usd = trade_val_jpy / rate

            trading_days = 0.0
            if pos.adv_10pct > 0:
                trading_days = round(trade_val_usd / pos.adv_10pct * 10) / 10

            signed = -trade_val_usd if side.startswith("Buy") else trade_val_usd

            key = f"{fund_name}:{matched}"
            exec_obj = ProposedExecution(
                fund=fund_name,
                symbol=matched,
                trade_type="Buy" if side.startswith("Buy") else "Sell",
                trade_quantity=trade_qty,
                target_raw=target_raw,
                trade_value_usd=trade_val_usd,
                trade_value_signed=signed,
                trading_days=trading_days,
                target_price=limit_px if limit_px > 0 else None,
            )
            if limit_px > 0:
                try:
                    pct = (limit_px / pos.price - 1) * 100
                    exec_obj.pct_to_curr = (
                        -abs(pct) if side.startswith("Buy") else abs(pct)
                    )
                except Exception:
                    pass

            self.proposed_executions[key] = exec_obj
            ok += 1
            symbols_done.add(matched)

        progress.close()

        if ok == 0:
            QMessageBox.warning(
                self,
                "Import Warning",
                f"No trades imported. {skipped} skipped.",
            )
            self.auto_sort_enabled = prev_sort
            return

        self._refresh_portfolio_display()
        self._update_proposed_trades_table()
        self._update_total_usd()
        if self.chart_visible:
            self._create_cash_path_chart()

        self.auto_sort_enabled = prev_sort

        if self.fund_names:
            self._sort_column = fund_column_index(0, 0)
            self._sort_reverse = False
            self._sort_portfolio_table(self._sort_column)

        QMessageBox.information(
            self,
            "Import Successful",
            f"Imported {ok} trades for {len(symbols_done)} symbols.\n"
            f"Skipped {skipped} trades.",
        )

    # =====================================================================
    #  IMPORT FILINGS
    # =====================================================================

    def _import_filings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Filings Excel File", "", "Excel files (*.xlsx);;All files (*.*)"
        )
        if not path:
            return
        progress = self._make_progress("Importing filings data...", 100)
        self._filings_worker = FilingsImportWorker(path)
        self._filings_worker.progress_updated.connect(
            lambda v, s: self._update_progress(progress, v, s)
        )
        self._filings_worker.import_completed.connect(self._on_filings_imported)
        self._filings_worker.import_error.connect(
            lambda msg: self._on_import_error(progress, msg)
        )
        self._filings_worker.start()

    def _on_filings_imported(self, filings) -> None:
        self.filings = filings
        self._refresh_filings_display()
        if not self.filings_visible:
            self._toggle_filings()
        QMessageBox.information(
            self, "Import Successful", f"Imported {len(filings)} filing records"
        )

    # =====================================================================
    #  PRICE REFRESH
    # =====================================================================

    def _refresh_prices(self) -> None:
        if not self.portfolio:
            return
        progress = self._make_progress("Refreshing prices...", len(self.portfolio))
        self._price_worker = PriceRefreshWorker(self.portfolio)
        self._price_worker.price_updated.connect(self._on_price_updated)
        self._price_worker.progress_updated.connect(progress.setValue)
        self._price_worker.completed.connect(progress.close)
        self._price_worker.error.connect(
            lambda msg: self._on_import_error(progress, msg)
        )
        self._price_worker.start()

    def _on_price_updated(self, symbol: str, price: float) -> None:
        if symbol == "USD/JPY":
            self.usd_jpy_rate = price
            self._exchange_rate_label.setText(f"USD/JPY: {price:.2f}")
            usd = self.portfolio.get("USD")
            if usd and usd.is_cash:
                usd.price = price
        elif symbol in self.portfolio:
            self.portfolio[symbol].price = price

    # =====================================================================
    #  DISPLAY REFRESH
    # =====================================================================

    def _refresh_portfolio_display(self) -> None:
        table = self._portfolio_table

        # remember selection
        selected_sym = None
        if table.selectionModel().hasSelection():
            row = table.currentRow()
            item = table.item(row, 1)
            if item:
                selected_sym = item.text()

        # snapshot existing rel-weight values
        existing_rw: dict[str, dict[str, float]] = {}
        for r in range(table.rowCount()):
            sym_item = table.item(r, 1)
            if not sym_item:
                continue
            sym = sym_item.text()
            existing_rw[sym] = {}
            for fi, fn in enumerate(self.fund_names):
                col = fund_column_index(fi, 0)
                rw_item = table.item(r, col)
                if rw_item and rw_item.text():
                    try:
                        existing_rw[sym][fn] = float(rw_item.text().replace("x", ""))
                    except ValueError:
                        pass

        # ensure exchange rate
        jpy = self.portfolio.get("JPY")
        if self.usd_jpy_rate <= 1.0 and jpy and jpy.is_cash and jpy.price > 1.0:
            self.usd_jpy_rate = jpy.price
            self._exchange_rate_label.setText(f"USD/JPY: {self.usd_jpy_rate:.2f}")

        rate = self.usd_jpy_rate if self.usd_jpy_rate > 0 else DEFAULT_EXCHANGE_RATE

        # ---- first pass: aggregate data ------------------------------------
        all_pos: dict[str, dict] = {}
        fund_totals_usd: dict[str, float] = {fn: 0.0 for fn in self.fund_names}
        positions_in_fund: dict[str, int] = {fn: 0 for fn in self.fund_names}

        for sym, pos in self.portfolio.items():
            if sym in CASH_SYMBOLS:
                continue
            row_data: dict = {
                "position": pos,
                "funds": {},
                "total_pct_of_company": 0.0,
            }
            for fn in self.fund_names:
                fp = pos.funds.get(fn)
                if fp is None:
                    continue
                val_jpy = pos.price * fp.quantity
                val_usd = val_jpy / rate
                fund_totals_usd[fn] += val_usd
                positions_in_fund[fn] += 1
                row_data["funds"][fn] = {"value_usd": val_usd, "fp": fp}
                row_data["total_pct_of_company"] += fp.pct_of_company
            if row_data["funds"]:
                all_pos[sym] = row_data

        # ---- second pass: weights ------------------------------------------
        for sym, rd in all_pos.items():
            for fn, fd in rd["funds"].items():
                total = fund_totals_usd[fn]
                n = positions_in_fund[fn]
                weight = (fd["value_usd"] / total * 100) if total > 0 else 0
                avg = 100.0 / n if n > 0 else 0

                if sym in existing_rw and fn in existing_rw[sym]:
                    rel = existing_rw[sym][fn]
                else:
                    rel = weight / avg if avg > 0 else 0

                key = f"{fn}:{sym}"
                new_rw = (
                    self.proposed_executions[key].target_raw
                    if key in self.proposed_executions
                    else 0.0
                )

                fd["weight"] = weight
                fd["rel_weight"] = rel
                fd["new_rel_weight"] = new_rw

        # ---- populate table ------------------------------------------------
        total_cols = NUM_FIXED_COLUMNS + NUM_FUND_COLUMNS * len(self.fund_names)
        table.setRowCount(0)
        table.setColumnCount(total_cols)

        headers = list(FIXED_COLUMNS)
        for fn in self.fund_names:
            for fc in FUND_COLUMNS:
                headers.append(f"{fn} - {fc}")
        table.setHorizontalHeaderLabels(headers)

        table.setColumnWidth(0, 40)
        table.setColumnWidth(1, 80)
        table.setColumnWidth(2, 150)
        for c in range(3, NUM_FIXED_COLUMNS):
            table.setColumnWidth(c, 100)
        for c in range(NUM_FIXED_COLUMNS, total_cols):
            table.setColumnWidth(c, 90)

        buy_qc = _qcolor(BUY_COLOR_RGB)
        sell_qc = _qcolor(SELL_COLOR_RGB)
        fund_qcolors = [_qcolor(c) for c in FUND_COLORS_RGB]

        row = 0
        for sym, rd in all_pos.items():
            pos: Position = rd["position"]
            table.insertRow(row)

            # detect trade direction
            has_buy = has_sell = False
            for fn in self.fund_names:
                k = f"{fn}:{sym}"
                if k in self.proposed_executions:
                    tt = self.proposed_executions[k].trade_type
                    if tt == "Buy":
                        has_buy = True
                    elif tt == "Sell":
                        has_sell = True

            row_color = None
            if has_buy and not has_sell:
                row_color = buy_qc
            elif has_sell and not has_buy:
                row_color = sell_qc

            items = [
                ("", Qt.AlignCenter),
                (sym, Qt.AlignLeft | Qt.AlignVCenter),
                (pos.name, Qt.AlignLeft | Qt.AlignVCenter),
                (f"{int(pos.price):,}", Qt.AlignRight | Qt.AlignVCenter),
                (
                    f"{rd['total_pct_of_company'] * 100:.2f}%",
                    Qt.AlignRight | Qt.AlignVCenter,
                ),
            ]
            for ci, (text, align) in enumerate(items):
                it = QTableWidgetItem(text)
                it.setTextAlignment(align)
                if row_color:
                    it.setBackground(QBrush(row_color))
                table.setItem(row, ci, it)

            for fi, fn in enumerate(self.fund_names):
                base = fund_column_index(fi, 0)
                fc = fund_qcolors[fi % len(fund_qcolors)]

                k = f"{fn}:{sym}"
                cell_color = fc
                if k in self.proposed_executions:
                    tt = self.proposed_executions[k].trade_type
                    cell_color = buy_qc if tt == "Buy" else sell_qc

                fd = rd["funds"].get(fn)
                if fd is None:
                    for sub in range(NUM_FUND_COLUMNS):
                        empty = QTableWidgetItem("")
                        empty.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        empty.setBackground(QBrush(cell_color))
                        table.setItem(row, base + sub, empty)
                    continue

                rw_item = QTableWidgetItem(f"{fd['rel_weight']:.2f}x")
                rw_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                rw_item.setBackground(QBrush(cell_color))
                table.setItem(row, base, rw_item)

                nrw = fd["new_rel_weight"]
                nrw_item = QTableWidgetItem(f"{nrw:.2f}x" if nrw else "")
                nrw_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                nrw_item.setBackground(QBrush(cell_color))
                table.setItem(row, base + 1, nrw_item)

            row += 1

        # restore selection
        if selected_sym:
            for r in range(table.rowCount()):
                si = table.item(r, 1)
                if si and si.text() == selected_sym:
                    table.selectRow(r)
                    break

        self._update_proposed_trades_table()
        self._update_total_usd()
        self._update_fund_headers()

        if (
            self._sort_column is not None
            and self.auto_sort_enabled
        ):
            self._sort_portfolio_table(self._sort_column)

    def _update_fund_headers(self) -> None:
        ht = self._header_table
        pt = self._portfolio_table
        cols = pt.columnCount()
        ht.setColumnCount(cols)
        for c in range(cols):
            ht.setColumnWidth(c, pt.columnWidth(c))
        ht.clearContents()
        for c in range(NUM_FIXED_COLUMNS):
            ht.setItem(0, c, QTableWidgetItem(""))

        fund_qcolors = [_qcolor(c) for c in FUND_COLORS_RGB]
        for fi, fn in enumerate(self.fund_names):
            first_col = fund_column_index(fi, 0)
            it = QTableWidgetItem(fn)
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(QBrush(fund_qcolors[fi % len(fund_qcolors)]))
            font = it.font()
            font.setBold(True)
            it.setFont(font)
            ht.setItem(0, first_col, it)
            ht.setSpan(0, first_col, 1, NUM_FUND_COLUMNS)

    # =====================================================================
    #  PROPOSED TRADES TABLE
    # =====================================================================

    def _update_proposed_trades_table(self) -> None:
        tbl = self._proposed_table
        tbl.setRowCount(0)
        if not self.proposed_executions:
            return

        by_sym: dict[str, dict] = {}
        for key, ex in self.proposed_executions.items():
            if ":" not in key:
                continue
            _, sym = key.split(":", 1)
            if sym not in self.portfolio:
                continue
            if sym not in by_sym:
                by_sym[sym] = {
                    "name": self.portfolio[sym].name,
                    "trade_type": ex.trade_type,
                    "total_shares": 0.0,
                    "total_value_usd": 0.0,
                    "funds": {},
                    "trading_days": 0.0,
                    "total_raw": 0.0,
                    "fund_count": 0,
                }
            entry = by_sym[sym]
            entry["funds"][key.split(":")[0]] = ex
            entry["total_shares"] += ex.trade_quantity
            entry["total_value_usd"] += ex.trade_value_usd
            entry["trading_days"] = max(entry["trading_days"], ex.trading_days or 0)
            entry["total_raw"] += ex.target_raw
            entry["fund_count"] += 1

        row = 0
        for sym, td in by_sym.items():
            if td["total_shares"] == 0 and td["total_value_usd"] == 0:
                continue
            tbl.insertRow(row)

            avg_raw = td["total_raw"] / td["fund_count"] if td["fund_count"] else 0
            tt = td["trade_type"]
            color = QColor("green") if tt == "Buy" else QColor("red")

            tp = pct = None
            for ex in td["funds"].values():
                if ex.target_price is not None:
                    tp = ex.target_price
                    pct = ex.pct_to_curr
                    break

            cells = [
                (tt, Qt.AlignLeft | Qt.AlignVCenter),
                (sym, Qt.AlignLeft | Qt.AlignVCenter),
                (td["name"], Qt.AlignLeft | Qt.AlignVCenter),
                (f"{int(abs(td['total_shares'])):,}", Qt.AlignRight | Qt.AlignVCenter),
                (f"{int(abs(td['total_value_usd'])):,}", Qt.AlignRight | Qt.AlignVCenter),
                (
                    f"{td['trading_days']:.1f}" if td["trading_days"] else "",
                    Qt.AlignRight | Qt.AlignVCenter,
                ),
                (f"{avg_raw:.2f}x", Qt.AlignRight | Qt.AlignVCenter),
                (f"{int(tp):,}" if tp is not None else "", Qt.AlignRight | Qt.AlignVCenter),
                (f"{pct:.1f}%" if pct is not None else "", Qt.AlignRight | Qt.AlignVCenter),
            ]
            for ci, (text, align) in enumerate(cells):
                it = QTableWidgetItem(text)
                it.setTextAlignment(align)
                if ci in (0, 3, 4):
                    it.setForeground(color)
                tbl.setItem(row, ci, it)
            row += 1

    def _update_total_usd(self) -> None:
        total = sum(
            ex.trade_value_signed for ex in self.proposed_executions.values()
        )
        self._total_usd_label.setText(f"Net Total: ${total:,.2f}")

    # =====================================================================
    #  FILINGS DISPLAY
    # =====================================================================

    def _refresh_filings_display(self) -> None:
        tbl = self._filings_table
        tbl.setRowCount(0)
        if not self.filings:
            return

        row = 0
        for sym, fd in self.filings.items():
            tbl.insertRow(row)
            tbl.setItem(row, 0, QTableWidgetItem(sym))
            tbl.setItem(row, 1, QTableWidgetItem(fd.name if hasattr(fd, 'name') else fd.get('name', '')))

            date_val = fd.date if hasattr(fd, 'date') else fd.get('date')
            tbl.setItem(row, 2, QTableWidgetItem(date_val or ""))

            last_filing = fd.last_filing if hasattr(fd, 'last_filing') else fd.get('last_filing')
            lf_text = f"{last_filing * 100:.2f}%" if last_filing is not None else ""
            lf_item = QTableWidgetItem(lf_text)
            lf_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tbl.setItem(row, 3, lf_item)

            # Current pct from portfolio
            current_pct = self._get_current_pct(sym)

            # Upward
            up_text = ""
            if current_pct is not None:
                if last_filing is not None:
                    up = (last_filing + 0.01) - current_pct
                else:
                    up = 0.05 - current_pct
                up_text = f"{up * 100:.2f}%"

            up_item = QTableWidgetItem(up_text)
            up_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if up_text:
                val = float(up_text.replace("%", ""))
                up_item.setBackground(
                    QBrush(QColor(255, 235, 156) if val > 0 else QColor(198, 239, 206))
                )
            tbl.setItem(row, 4, up_item)

            # Downward
            down_text = ""
            if current_pct is not None and last_filing is not None:
                down = current_pct - (last_filing - 0.01)
                down_text = f"{down * 100:.2f}%"

            down_item = QTableWidgetItem(down_text)
            down_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if down_text:
                val = float(down_text.replace("%", ""))
                down_item.setBackground(
                    QBrush(
                        QColor(198, 239, 206) if val > 0 else QColor(255, 199, 206)
                    )
                )
            tbl.setItem(row, 5, down_item)
            row += 1

    def _get_current_pct(self, symbol: str) -> float | None:
        pos = self.portfolio.get(symbol)
        if pos is None:
            return None
        pct = pos.total_pct_of_company
        if pct:
            return pct
        if pos.os_shares > 0 and pos.total_quantity > 0:
            return pos.total_quantity / pos.os_shares
        return None

    def _toggle_filings(self) -> None:
        if self.filings_visible:
            self._middle_panel.setVisible(False)
            self.filings_visible = False
            self._show_filings_btn.setVisible(True)
            self._main_splitter.setSizes([1050, 0, 350])
        else:
            self._middle_panel.setVisible(True)
            self.filings_visible = True
            self._show_filings_btn.setVisible(False)
            self._refresh_filings_display()
            self._main_splitter.setSizes([700, 350, 350])

    def _sort_filings_table(self, col_index: int) -> None:
        tbl = self._filings_table
        header = tbl.horizontalHeaderItem(col_index).text()
        attr = "_filings_sort_col"

        if getattr(self, attr, None) == col_index:
            rev = not getattr(self, "_filings_sort_rev", False)
        else:
            rev = False
        setattr(self, attr, col_index)
        self._filings_sort_rev = rev

        data = []
        for r in range(tbl.rowCount()):
            data.append([tbl.item(r, c).text() if tbl.item(r, c) else "" for c in range(tbl.columnCount())])

        def key_fn(rd):
            v = rd[col_index]
            if not v:
                return -999999 if ("Filing" in header or "%" in header) else ""
            if "%" in header:
                try:
                    return float(v.replace("%", ""))
                except ValueError:
                    return -999999
            if header == "Date":
                try:
                    return datetime.strptime(v, "%Y-%m-%d")
                except ValueError:
                    return datetime.min
            return v

        data.sort(key=key_fn, reverse=rev)
        tbl.setSortingEnabled(False)
        for r, rd in enumerate(data):
            for c, txt in enumerate(rd):
                it = tbl.item(r, c)
                if it:
                    it.setText(txt)
        tbl.setSortingEnabled(True)

    # =====================================================================
    #  POSITION DETAILS
    # =====================================================================

    def _on_position_select(self) -> None:
        sel = self._portfolio_table.selectedItems()
        if not sel:
            self._clear_position_details()
            return

        row = sel[0].row()
        sym_item = self._portfolio_table.item(row, 1)
        if not sym_item:
            return
        sym = sym_item.text()
        pos = self.portfolio.get(sym)
        if not pos:
            return

        total_qty = pos.total_quantity
        val_jpy = pos.price * total_qty
        rate = self.usd_jpy_rate if self.usd_jpy_rate > 0 else DEFAULT_EXCHANGE_RATE
        val_usd = val_jpy / rate

        total_usd = 0.0
        n_positions = 0
        for s, p in self.portfolio.items():
            if s in CASH_SYMBOLS:
                continue
            n_positions += 1
            total_usd += p.price * p.total_quantity / rate

        weight = (val_usd / total_usd * 100) if total_usd > 0 else 0
        avg = 100.0 / n_positions if n_positions > 0 else 0
        rel = weight / avg if avg > 0 else 0

        labels = self._pos_labels
        labels["Symbol:"].setText(sym)
        labels["Name:"].setText(pos.name)
        labels["Price (JPY):"].setText(f"{pos.price:,.2f}")
        labels["Quantity:"].setText(f"{total_qty:,.2f}")
        labels["Value (JPY):"].setText(f"{val_jpy:,.2f}")
        labels["Value (USD):"].setText(f"{val_usd:,.2f}")
        labels["Weight:"].setText(f"{weight:.2f}%")
        labels["Current Rel. Weight:"].setText(f"{rel:.2f}x")

    def _clear_position_details(self) -> None:
        for lbl in self._pos_labels.values():
            lbl.setText("")

    # =====================================================================
    #  TRADE DIALOGS
    # =====================================================================

    def _on_portfolio_dbl_click(self, row, _col) -> None:
        self._portfolio_table.selectRow(row)
        self._open_trade_dialog()

    def _open_trade_dialog(self) -> None:
        if not self._portfolio_table.selectionModel().hasSelection():
            QMessageBox.information(self, "Info", "Please select a position to trade")
            return

        row = self._portfolio_table.currentRow()
        sym_item = self._portfolio_table.item(row, 1)
        if not sym_item:
            return
        sym = sym_item.text()
        pos = self.portfolio.get(sym)
        if not pos:
            return

        dlg = TradeDialog(
            parent=self,
            symbol=sym,
            position=pos,
            portfolio=self.portfolio,
            fund_names=self.fund_names,
            proposed_executions=self.proposed_executions,
            usd_jpy_rate=self.usd_jpy_rate,
            filings=self.filings,
            portfolio_table=self._portfolio_table,
        )
        if dlg.exec_() != TradeDialog.Accepted:
            return

        for fund_name, trade_info in dlg.result_trades.items():
            tt = trade_info["trade_type"]
            tq = trade_info["trade_quantity"]
            raw = trade_info["target_raw"]
            usd = trade_info["trade_value_usd"]

            trading_days = 0.0
            if pos.adv_10pct > 0:
                trading_days = round(abs(usd) / pos.adv_10pct * 10) / 10

            signed = -usd if tt == "Buy" else usd
            key = f"{fund_name}:{sym}"

            self.proposed_executions[key] = ProposedExecution(
                fund=fund_name,
                symbol=sym,
                trade_type=tt,
                trade_quantity=tq,
                target_raw=raw,
                trade_value_usd=usd,
                trade_value_signed=signed,
                trading_days=trading_days,
            )

        self._apply_trade_to_table(sym)
        self._update_proposed_trades_table()
        self._update_total_usd()
        if self.chart_visible:
            self._create_cash_path_chart()

    def _apply_trade_to_table(self, symbol: str) -> None:
        """Update just the affected rows in the portfolio table after a trade."""
        table = self._portfolio_table
        buy_qc = _qcolor(BUY_COLOR_RGB)
        sell_qc = _qcolor(SELL_COLOR_RGB)

        for r in range(table.rowCount()):
            si = table.item(r, 1)
            if not si or si.text() != symbol:
                continue

            has_buy = has_sell = False
            for fi, fn in enumerate(self.fund_names):
                k = f"{fn}:{symbol}"
                base = fund_column_index(fi, 0)
                if k in self.proposed_executions:
                    ex = self.proposed_executions[k]
                    if ex.trade_type == "Buy":
                        has_buy = True
                    else:
                        has_sell = True
                    nrw = table.item(r, base + 1)
                    if nrw:
                        nrw.setText(f"{ex.target_raw:.2f}x")
                        nrw.setBackground(
                            QBrush(buy_qc if ex.trade_type == "Buy" else sell_qc)
                        )

            if has_buy and not has_sell:
                rc = buy_qc
            elif has_sell and not has_buy:
                rc = sell_qc
            else:
                rc = None

            if rc:
                for c in range(NUM_FIXED_COLUMNS):
                    it = table.item(r, c)
                    if it:
                        it.setBackground(QBrush(rc))
            break

    def _on_proposed_trade_dbl_click(self, row, col) -> None:
        if col == 7:
            self._edit_target_price(row)

    def _edit_target_price(self, row: int) -> None:
        sym_item = self._proposed_table.item(row, 1)
        if not sym_item:
            return
        sym = sym_item.text()
        pos = self.portfolio.get(sym)
        if not pos:
            return

        fund_execs = {
            k.split(":")[0]: ex
            for k, ex in self.proposed_executions.items()
            if ":" in k and k.split(":", 1)[1] == sym
        }
        if not fund_execs:
            return

        current_tp = next(
            (ex.target_price for ex in fund_execs.values() if ex.target_price), 0
        )
        dlg = TargetPriceDialog(self, sym, pos.price, current_tp)
        if dlg.exec_() != TargetPriceDialog.Accepted or dlg.target_price is None:
            return

        tp = dlg.target_price
        for ex in fund_execs.values():
            ex.target_price = tp
            pct = (tp / pos.price - 1) * 100
            ex.pct_to_curr = -abs(pct) if ex.trade_type == "Buy" else abs(pct)

        # update table cells
        avg_pct = sum(ex.pct_to_curr for ex in fund_execs.values() if ex.pct_to_curr is not None) / max(
            sum(1 for ex in fund_execs.values() if ex.pct_to_curr is not None), 1
        )
        self._proposed_table.item(row, 7).setText(f"{int(tp):,}")
        self._proposed_table.item(row, 8).setText(f"{avg_pct:.1f}%")

        if self.chart_visible:
            self._create_cash_path_chart()

    def _on_proposed_trade_select(self) -> None:
        has = bool(self._proposed_table.selectedItems())
        self._edit_trade_btn.setEnabled(has)
        self._delete_trade_btn.setEnabled(has)

    def _edit_proposed_trade(self) -> None:
        if not self._proposed_table.selectedItems():
            return
        row = self._proposed_table.currentRow()
        sym_item = self._proposed_table.item(row, 1)
        if not sym_item:
            return
        sym = sym_item.text()

        # re-open the trade dialog for this symbol
        pos = self.portfolio.get(sym)
        if not pos:
            return

        # select the matching row in portfolio table
        for r in range(self._portfolio_table.rowCount()):
            si = self._portfolio_table.item(r, 1)
            if si and si.text() == sym:
                self._portfolio_table.selectRow(r)
                break

        self._open_trade_dialog()

    def _delete_proposed_trade(self) -> None:
        if not self._proposed_table.selectedItems():
            return
        row = self._proposed_table.currentRow()
        sym_item = self._proposed_table.item(row, 1)
        if not sym_item:
            return
        sym = sym_item.text()

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Delete proposed trade for {sym}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        keys = [k for k in self.proposed_executions if k.endswith(f":{sym}")]
        for k in keys:
            del self.proposed_executions[k]

        self._proposed_table.removeRow(row)
        self._update_total_usd()
        self._refresh_portfolio_display()
        if self.chart_visible:
            self._create_cash_path_chart()
        self._edit_trade_btn.setEnabled(False)
        self._delete_trade_btn.setEnabled(False)

    def _clear_proposed_executions(self) -> None:
        if not self.proposed_executions:
            return
        reply = QMessageBox.question(
            self,
            "Confirm Clear All",
            "Clear all proposed trades?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        affected = {k.split(":", 1)[1] for k in self.proposed_executions if ":" in k}
        self.proposed_executions.clear()
        self._proposed_table.setRowCount(0)
        self._update_total_usd()

        # reset affected rows
        table = self._portfolio_table
        fund_qcolors = [_qcolor(c) for c in FUND_COLORS_RGB]
        for r in range(table.rowCount()):
            si = table.item(r, 1)
            if not si or si.text() not in affected:
                continue
            for fi, fn in enumerate(self.fund_names):
                nrw_col = fund_column_index(fi, 1)
                it = table.item(r, nrw_col)
                if it:
                    it.setText("")
                    it.setBackground(QBrush(fund_qcolors[fi % len(fund_qcolors)]))
            for c in range(NUM_FIXED_COLUMNS):
                it = table.item(r, c)
                if it:
                    it.setBackground(QBrush(Qt.white))

        if self.chart_visible:
            self._create_cash_path_chart()

    # =====================================================================
    #  ADD / REMOVE POSITIONS
    # =====================================================================

    def _add_position_dialog(self) -> None:
        dlg = AddPositionDialog(self, self.fund_names, self.usd_jpy_rate)
        if dlg.exec_() != AddPositionDialog.Accepted or dlg.result_position is None:
            return

        pos = dlg.result_position
        pos.funds = {}
        for fn, qty in dlg.result_fund_quantities.items():
            pos.funds[fn] = FundPosition(quantity=qty)
            if fn not in self.fund_names:
                self.fund_names.append(fn)

        self.portfolio[pos.symbol] = pos
        self._refresh_portfolio_display()

    def _remove_position(self) -> None:
        if not self._portfolio_table.selectionModel().hasSelection():
            QMessageBox.information(self, "Info", "Please select a position to remove")
            return

        row = self._portfolio_table.currentRow()
        sym_item = self._portfolio_table.item(row, 1)
        if not sym_item:
            return
        sym = sym_item.text()

        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Remove {sym} from the portfolio?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.portfolio.pop(sym, None)
        keys = [k for k in self.proposed_executions if k.endswith(f":{sym}")]
        for k in keys:
            del self.proposed_executions[k]

        self._refresh_portfolio_display()
        self._clear_position_details()
        if self.chart_visible:
            self._create_cash_path_chart()

    # =====================================================================
    #  SORTING
    # =====================================================================

    def _sort_portfolio_table(self, col_index: int) -> None:
        if self._sort_column == col_index:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = col_index
            self._sort_reverse = False

        table = self._portfolio_table
        header = table.horizontalHeaderItem(col_index)
        if not header:
            return
        header_text = header.text()

        selected_sym = None
        if table.selectionModel().hasSelection():
            si = table.item(table.currentRow(), 1)
            if si:
                selected_sym = si.text()

        rows_data = []
        for r in range(table.rowCount()):
            row_texts = []
            for c in range(table.columnCount()):
                it = table.item(r, c)
                row_texts.append(it.text() if it else "")
            rows_data.append(row_texts)

        def sort_key(rd):
            v = rd[col_index]
            if not v:
                if any(kw in header_text for kw in ("Price", "Value", "Weight", "Quantity", "% of Company")):
                    return 0.0
                return ""
            if "Price" in header_text or "Value" in header_text:
                return float(v.replace(",", "").replace("$", "").replace("¥", "") or "0")
            if "% of Company" in header_text and "%" in v:
                return float(v.replace("%", ""))
            if "Weight" in header_text and "%" in v:
                return float(v.replace("%", ""))
            if "Weight" in header_text and "x" in v:
                return float(v.replace("x", ""))
            if "Quantity" in header_text or "Shares" in header_text:
                return float(v.replace(",", "").replace("+", "").replace("-", "") or "0")
            return v

        rows_data.sort(key=sort_key, reverse=self._sort_reverse)

        table.setSortingEnabled(False)
        for r, rd in enumerate(rows_data):
            for c, txt in enumerate(rd):
                it = table.item(r, c)
                if it:
                    it.setText(txt)

        for r in range(table.rowCount()):
            it = table.item(r, 0)
            if it:
                it.setText(str(r + 1))
                it.setTextAlignment(Qt.AlignCenter)
        table.setSortingEnabled(True)

        if selected_sym:
            for r in range(table.rowCount()):
                si = table.item(r, 1)
                if si and si.text() == selected_sym:
                    table.selectRow(r)
                    break

    # =====================================================================
    #  CASH PATH CHARTS
    # =====================================================================

    def _toggle_cash_path(self) -> None:
        if self.chart_visible:
            self._chart_frame.setVisible(False)
            self.chart_visible = False
            self._cash_path_btn.setText("Show Cash Path")
            self._right_splitter.setSizes([1, 0])
        else:
            self._create_cash_path_chart()
            self._chart_frame.setVisible(True)
            self.chart_visible = True
            self._cash_path_btn.setText("Hide Cash Path")
            h = self._right_splitter.size().height()
            self._right_splitter.setSizes([h // 2, h // 2])

    def _create_cash_path_chart(self) -> None:
        for i in reversed(range(self._chart_layout.count())):
            self._chart_layout.itemAt(i).widget().deleteLater()

        if not self.proposed_executions:
            self._chart_layout.addWidget(QLabel("No proposed trades to chart"))
            return

        fund_execs: dict[str, list[dict]] = {}
        for key, ex in self.proposed_executions.items():
            if ":" not in key:
                continue
            fn = key.split(":")[0]
            fund_execs.setdefault(fn, []).append(
                {"symbol": key.split(":", 1)[1], "execution": ex}
            )

        if not fund_execs:
            self._chart_layout.addWidget(QLabel("No fund-specific trades to chart"))
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        sw = QWidget()
        sl = QVBoxLayout(sw)

        for fn, execs in fund_execs.items():
            max_days = max(
                (math.ceil(e["execution"].trading_days) for e in execs if e["execution"].trading_days),
                default=0,
            )
            if max_days == 0:
                continue

            initial = self._get_fund_cash_usd(fn)
            canvas, cur, mn, end = build_cash_path_chart(
                fn, execs, self.portfolio, max_days, initial
            )

            group = QGroupBox(f"Cash Path for {fn}")
            gl = QVBoxLayout(group)

            header = QHBoxLayout()
            header.addWidget(QLabel(f"Current: ${cur:.2f}mm"))
            header.addWidget(QLabel(f"Minimum: ${mn:.2f}mm"))
            header.addWidget(QLabel(f"Ending: ${end:.2f}mm"))
            net = end - cur
            nl = QLabel(f"Net Change: ${net:.2f}mm")
            nl.setStyleSheet("color: green;" if net > 0 else "color: red;" if net < 0 else "")
            header.addWidget(nl)
            header.addStretch()
            gl.addLayout(header)
            gl.addWidget(canvas)
            sl.addWidget(group)

        scroll.setWidget(sw)
        self._chart_layout.addWidget(scroll)

    def _get_fund_cash_usd(self, fund_name: str) -> float:
        total = 0.0
        rate = self.usd_jpy_rate if self.usd_jpy_rate > 0 else DEFAULT_EXCHANGE_RATE
        for sym in ("JPY", "USD"):
            pos = self.portfolio.get(sym)
            if not pos or not pos.is_cash:
                continue
            fp = pos.funds.get(fund_name)
            if not fp:
                continue
            if sym == "JPY":
                total += fp.quantity / rate
            else:
                total += fp.quantity
        return total

    # =====================================================================
    #  EXPORT
    # =====================================================================

    def _export_proposed_trades(self) -> None:
        if not self.proposed_executions:
            QMessageBox.information(self, "Info", "No proposed trades to export")
            return

        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        default = os.path.join(
            desktop,
            f"proposed_trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Proposed Trades", default, "Excel files (*.xlsx);;All files (*.*)"
        )
        if not path:
            return

        try:
            rows = []
            for key, ex in self.proposed_executions.items():
                if ":" not in key:
                    continue
                fn, sym = key.split(":", 1)
                pos = self.portfolio.get(sym)
                signed = -ex.trade_value_usd if ex.trade_type == "Buy" else ex.trade_value_usd
                rows.append({
                    "Fund": fn,
                    "Trade Type": ex.trade_type,
                    "Symbol": sym,
                    "Name": pos.name if pos else "",
                    "Price": pos.price if pos else 0,
                    "Quantity": ex.trade_quantity,
                    "USD Value": signed,
                    "Trading Days": ex.trading_days,
                    "Target RAW": ex.target_raw,
                    "Target Price": ex.target_price if ex.target_price is not None else "",
                    "% to Curr Price": ex.pct_to_curr if ex.pct_to_curr is not None else "",
                })

            pd.DataFrame(rows).to_excel(path, index=False)
            QMessageBox.information(self, "Success", f"Exported to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Export error: {exc}")

    # =====================================================================
    #  PROGRESS HELPERS
    # =====================================================================

    def _make_progress(self, text: str, maximum: int) -> QProgressDialog:
        p = QProgressDialog(text, "Cancel", 0, maximum, self)
        p.setWindowModality(Qt.WindowModal)
        p.setValue(0)
        p.show()
        return p

    @staticmethod
    def _update_progress(dlg: QProgressDialog, value: int, status: str) -> None:
        dlg.setValue(value)
        dlg.setLabelText(status)

    @staticmethod
    def _on_import_error(dlg: QProgressDialog, msg: str) -> None:
        dlg.close()
        QMessageBox.critical(None, "Import Error", msg)
