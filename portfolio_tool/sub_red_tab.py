"""Subscription / Redemption tab for Paradaim Portfolio.Tool."""

from __future__ import annotations

import math

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QGridLayout,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import (
    CASH_SYMBOLS,
    DEFAULT_EXCHANGE_RATE,
    FIXED_COLUMNS,
    FUND_COLORS_RGB,
    FUND_COLUMNS,
    NUM_FIXED_COLUMNS,
    NUM_FUND_COLUMNS,
    FundPosition,
    Position,
    calculate_value_usd,
    fund_column_index,
)
from .workers import (
    ExchangeRateWorker,
    PortfolioImportWorker,
    PriceRefreshWorker,
)


def _qcolor(rgb: tuple[int, int, int]) -> QColor:
    return QColor(*rgb)


# ---------------------------------------------------------------------------
# Schedule computation
# ---------------------------------------------------------------------------

def compute_schedule(
    portfolio: dict[str, Position],
    fund_names: list[str],
    amount_usd: float,
    usd_jpy_rate: float,
    mode: str,  # "maintain_weights" or "minimize_time"
    direction: str,  # "subscription" or "redemption"
) -> list[dict]:
    """Compute a weekly trading schedule.

    Returns a list of dicts, one per non-cash position:
        {
            "symbol": str,
            "name": str,
            "current_value_usd": float,
            "target_change_usd": float,
            "trading_days": float,
            "weeks": [float, ...],  # USD traded per week
        }
    """
    rate = usd_jpy_rate if usd_jpy_rate > 0 else DEFAULT_EXCHANGE_RATE

    # Compute current portfolio value (non-cash only)
    positions: list[dict] = []
    total_value_usd = 0.0

    for sym, pos in portfolio.items():
        if sym in CASH_SYMBOLS or pos.is_cash:
            continue
        total_qty = pos.total_quantity
        if total_qty <= 0:
            continue
        val_jpy = pos.price * total_qty
        val_usd = val_jpy / rate
        total_value_usd += val_usd
        positions.append({
            "symbol": sym,
            "name": pos.name,
            "current_value_usd": val_usd,
            "adv_10pct": pos.adv_10pct,
            "price": pos.price,
        })

    if total_value_usd <= 0 or not positions:
        return []

    # Allocate the subscription/redemption amount proportionally by weight
    results: list[dict] = []
    for p in positions:
        weight = p["current_value_usd"] / total_value_usd
        change_usd = amount_usd * weight  # always positive
        adv = p["adv_10pct"]

        if adv > 0:
            trading_days = change_usd / adv
        else:
            trading_days = 0.0

        results.append({
            "symbol": p["symbol"],
            "name": p["name"],
            "current_value_usd": p["current_value_usd"],
            "target_change_usd": change_usd,
            "adv_10pct": adv,
            "trading_days_raw": trading_days,
            "trading_days": 0.0,
            "weeks": [],
        })

    if mode == "minimize_time":
        _schedule_minimize_time(results)
    else:
        _schedule_maintain_weights(results)

    return results


def _schedule_minimize_time(results: list[dict]) -> None:
    """Each position trades independently at up to 10% ADV per day."""
    for r in results:
        td = r["trading_days_raw"]
        r["trading_days"] = td
        if td <= 0 or r["adv_10pct"] <= 0:
            continue

        remaining = r["target_change_usd"]
        daily_cap = r["adv_10pct"]
        weekly_cap = 5 * daily_cap
        weeks = []

        while remaining > 1e-6:
            week_trade = min(weekly_cap, remaining)
            weeks.append(week_trade)
            remaining -= week_trade

        r["weeks"] = weeks


def _schedule_maintain_weights(results: list[dict]) -> None:
    """All positions must maintain relative weights throughout the process.

    The bottleneck position (highest trading_days_raw) dictates the pace.
    All other positions slow down proportionally.
    """
    if not results:
        return

    # The bottleneck is the position requiring the most trading days
    bottleneck_days = max(r["trading_days_raw"] for r in results)
    if bottleneck_days <= 0:
        return

    for r in results:
        r["trading_days"] = bottleneck_days

        if r["target_change_usd"] <= 0:
            continue

        # Daily trade for this position = total / bottleneck_days
        daily_trade = r["target_change_usd"] / bottleneck_days
        weekly_trade = 5 * daily_trade
        remaining = r["target_change_usd"]
        weeks = []

        while remaining > 1e-6:
            week_trade = min(weekly_trade, remaining)
            weeks.append(week_trade)
            remaining -= week_trade

        r["weeks"] = weeks


# ---------------------------------------------------------------------------
# Subscription/Redemption Input Dialog
# ---------------------------------------------------------------------------

class SubRedInputDialog(QDialog):
    """Dialog to enter subscription or redemption parameters."""

    def __init__(self, parent, title: str, usd_jpy_rate: float):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(420, 220)
        self.usd_jpy_rate = usd_jpy_rate

        self.result_amount_usd: float = 0.0
        self.result_mode: str = ""  # "maintain_weights" or "minimize_time"

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Amount inputs
        amount_group = QGroupBox("Amount")
        ag = QGridLayout(amount_group)

        ag.addWidget(QLabel("JPY (billions):"), 0, 0)
        self._jpy_input = QLineEdit()
        self._jpy_input.setPlaceholderText("e.g. 50")
        self._jpy_input.textChanged.connect(self._on_jpy_changed)
        ag.addWidget(self._jpy_input, 0, 1)

        ag.addWidget(QLabel("USD (millions):"), 1, 0)
        self._usd_input = QLineEdit()
        self._usd_input.setPlaceholderText("e.g. 500")
        self._usd_input.textChanged.connect(self._on_usd_changed)
        ag.addWidget(self._usd_input, 1, 1)

        rate_text = f"(USD/JPY: {self.usd_jpy_rate:.2f})" if self.usd_jpy_rate > 0 else ""
        ag.addWidget(QLabel(rate_text), 2, 0, 1, 2)

        layout.addWidget(amount_group)

        # Mode selection
        mode_group = QGroupBox("Execution Mode")
        ml = QVBoxLayout(mode_group)
        self._mode_group = QButtonGroup(self)

        self._maintain_radio = QRadioButton("Maintain Weights")
        self._maintain_radio.setToolTip(
            "Maintain relative average weights throughout the process.\n"
            "Slower positions dictate the pace for all."
        )
        self._maintain_radio.setChecked(True)
        self._mode_group.addButton(self._maintain_radio)
        ml.addWidget(self._maintain_radio)

        self._minimize_radio = QRadioButton("Minimize Time")
        self._minimize_radio.setToolTip(
            "Each position trades independently at up to 10% ADV per day.\n"
            "Most liquid / smallest positions fill first."
        )
        self._mode_group.addButton(self._minimize_radio)
        ml.addWidget(self._minimize_radio)

        layout.addWidget(mode_group)

        # Buttons
        btns = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        btns.addStretch()
        submit = QPushButton("Calculate")
        submit.clicked.connect(self._on_submit)
        btns.addWidget(submit)
        layout.addLayout(btns)

        # Track which field was last edited
        self._last_edited = None

    def _on_jpy_changed(self, text: str) -> None:
        self._last_edited = "jpy"
        if not text:
            return
        try:
            jpy_billions = float(text)
            rate = self.usd_jpy_rate if self.usd_jpy_rate > 0 else DEFAULT_EXCHANGE_RATE
            usd_millions = (jpy_billions * 1e9) / rate / 1e6
            self._usd_input.blockSignals(True)
            self._usd_input.setText(f"{usd_millions:.2f}")
            self._usd_input.blockSignals(False)
        except ValueError:
            pass

    def _on_usd_changed(self, text: str) -> None:
        self._last_edited = "usd"
        if not text:
            return
        try:
            usd_millions = float(text)
            rate = self.usd_jpy_rate if self.usd_jpy_rate > 0 else DEFAULT_EXCHANGE_RATE
            jpy_billions = (usd_millions * 1e6) * rate / 1e9
            self._jpy_input.blockSignals(True)
            self._jpy_input.setText(f"{jpy_billions:.2f}")
            self._jpy_input.blockSignals(False)
        except ValueError:
            pass

    def _on_submit(self) -> None:
        try:
            usd_text = self._usd_input.text().strip()
            if not usd_text:
                QMessageBox.critical(self, "Error", "Please enter an amount")
                return
            usd_millions = float(usd_text)
            if usd_millions <= 0:
                QMessageBox.critical(self, "Error", "Amount must be positive")
                return
            self.result_amount_usd = usd_millions * 1e6  # convert to actual USD
        except ValueError:
            QMessageBox.critical(self, "Error", "Invalid amount")
            return

        if self._maintain_radio.isChecked():
            self.result_mode = "maintain_weights"
        else:
            self.result_mode = "minimize_time"

        self.accept()


# ---------------------------------------------------------------------------
# Subscription/Redemption Tab
# ---------------------------------------------------------------------------

class SubscriptionRedemptionTab(QWidget):
    """The Subscription/Redemption tab content."""

    def __init__(self, main_window: QMainWindow) -> None:
        super().__init__()
        self._main = main_window

        # Own portfolio state (independent of Current Portfolio tab)
        self.portfolio: dict[str, Position] = {}
        self.usd_jpy_rate: float = 0.0
        self.fund_names: list[str] = []
        # Schedule results
        self._schedule: list[dict] = []
        self._schedule_direction: str = ""
        self._schedule_mode: str = ""
        self._schedule_amount_usd: float = 0.0

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Top: Portfolio section
        portfolio_group = QGroupBox("Portfolio")
        pg_layout = QVBoxLayout(portfolio_group)

        top_btns = QHBoxLayout()
        top_btns.addWidget(self._btn("Import Portfolio", self._import_portfolio))
        top_btns.addWidget(self._btn("Refresh Prices", self._refresh_prices))
        top_btns.addStretch()
        top_btns.addWidget(self._btn("Create Subscription", self._create_subscription))
        top_btns.addWidget(self._btn("Create Redemption", self._create_redemption))
        pg_layout.addLayout(top_btns)

        # Portfolio table
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
        self._portfolio_table.horizontalScrollBar().valueChanged.connect(
            self._header_table.horizontalScrollBar().setValue
        )

        cl.addWidget(self._header_table)
        cl.addWidget(self._portfolio_table)
        pg_layout.addWidget(container)

        # Exchange rate label
        bottom = QHBoxLayout()
        bottom.addStretch()
        self._exchange_rate_label = QLabel("USD/JPY: —")
        bottom.addWidget(self._exchange_rate_label)
        pg_layout.addLayout(bottom)

        layout.addWidget(portfolio_group)

        # Bottom: Schedule results
        self._schedule_group = QGroupBox("Execution Schedule")
        sg_layout = QVBoxLayout(self._schedule_group)

        self._schedule_info_label = QLabel("")
        sg_layout.addWidget(self._schedule_info_label)

        self._schedule_table = QTableWidget()
        self._schedule_table.setAlternatingRowColors(True)
        self._schedule_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._schedule_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._schedule_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        self._schedule_table.horizontalHeader().setStretchLastSection(False)
        self._schedule_table.verticalHeader().setVisible(False)
        self._schedule_table.setStyleSheet(
            "QTableWidget::item { border-right: 0px; padding: 6px; }"
            "QHeaderView::section { border-right: 0px; }"
        )
        sg_layout.addWidget(self._schedule_table)

        layout.addWidget(self._schedule_group)

    @staticmethod
    def _btn(text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(slot)
        return b

    # =====================================================================
    #  IMPORT / PRICES
    # =====================================================================

    def _import_portfolio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel File", "", "Excel files (*.xlsx);;All files (*.*)"
        )
        if not path:
            return

        progress = self._make_progress("Importing portfolio data...", 100)

        self._import_worker = PortfolioImportWorker(path)
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

    def _refresh_prices(self) -> None:
        if not self.portfolio:
            return
        progress = self._make_progress("Refreshing prices...", 100)
        self._price_worker = PriceRefreshWorker(self.portfolio)
        self._price_worker.price_updated.connect(self._on_price_updated)
        self._price_worker.progress_updated.connect(
            lambda v, s: self._update_progress(progress, v, s)
        )
        self._price_worker.completed.connect(progress.close)
        self._price_worker.completed.connect(self._refresh_portfolio_display)
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
    #  PORTFOLIO DISPLAY
    # =====================================================================

    def _refresh_portfolio_display(self) -> None:
        table = self._portfolio_table
        rate = self.usd_jpy_rate if self.usd_jpy_rate > 0 else DEFAULT_EXCHANGE_RATE

        # Aggregate data
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

        # Compute weights
        for sym, rd in all_pos.items():
            for fn, fd in rd["funds"].items():
                total = fund_totals_usd[fn]
                n = positions_in_fund[fn]
                weight = (fd["value_usd"] / total * 100) if total > 0 else 0
                avg = 100.0 / n if n > 0 else 0
                rel = weight / avg if avg > 0 else 0
                fd["weight"] = weight
                fd["rel_weight"] = rel

        # Populate table
        total_cols = NUM_FIXED_COLUMNS + len(self.fund_names)  # one col per fund (Curr. weight)
        table.setRowCount(0)
        table.setColumnCount(total_cols)

        headers = list(FIXED_COLUMNS)
        for fn in self.fund_names:
            headers.append(f"{fn} - Wt")
        table.setHorizontalHeaderLabels(headers)

        table.setColumnWidth(0, 40)
        table.setColumnWidth(1, 80)
        table.setColumnWidth(2, 150)
        for c in range(3, NUM_FIXED_COLUMNS):
            table.setColumnWidth(c, 100)
        for c in range(NUM_FIXED_COLUMNS, total_cols):
            table.setColumnWidth(c, 90)

        fund_qcolors = [_qcolor(c) for c in FUND_COLORS_RGB]

        row = 0
        for sym, rd in all_pos.items():
            pos: Position = rd["position"]
            table.insertRow(row)

            items = [
                (str(row + 1), Qt.AlignCenter),
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
                table.setItem(row, ci, it)

            for fi, fn in enumerate(self.fund_names):
                col = NUM_FIXED_COLUMNS + fi
                fc = fund_qcolors[fi % len(fund_qcolors)]
                fd = rd["funds"].get(fn)
                if fd is None:
                    empty = QTableWidgetItem("")
                    empty.setBackground(QBrush(fc))
                    table.setItem(row, col, empty)
                    continue
                rw_item = QTableWidgetItem(f"{fd['rel_weight']:.2f}x")
                rw_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                rw_item.setBackground(QBrush(fc))
                table.setItem(row, col, rw_item)

            row += 1

        self._update_fund_headers()

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
            col = NUM_FIXED_COLUMNS + fi
            it = QTableWidgetItem(fn)
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(QBrush(fund_qcolors[fi % len(fund_qcolors)]))
            font = it.font()
            font.setBold(True)
            it.setFont(font)
            ht.setItem(0, col, it)

    # =====================================================================
    #  SUBSCRIPTION / REDEMPTION
    # =====================================================================

    def _create_subscription(self) -> None:
        self._run_sub_red("subscription")

    def _create_redemption(self) -> None:
        self._run_sub_red("redemption")

    def _run_sub_red(self, direction: str) -> None:
        if not self.portfolio:
            QMessageBox.warning(self, "Warning", "Please import a portfolio first.")
            return

        title = "Create Subscription" if direction == "subscription" else "Create Redemption"
        dlg = SubRedInputDialog(self, title, self.usd_jpy_rate)
        if dlg.exec_() != QDialog.Accepted:
            return

        amount_usd = dlg.result_amount_usd
        mode = dlg.result_mode

        # Validate redemption doesn't exceed portfolio
        if direction == "redemption":
            rate = self.usd_jpy_rate if self.usd_jpy_rate > 0 else DEFAULT_EXCHANGE_RATE
            total_portfolio_usd = 0.0
            for sym, pos in self.portfolio.items():
                if sym in CASH_SYMBOLS or pos.is_cash:
                    continue
                total_portfolio_usd += pos.price * pos.total_quantity / rate
            if amount_usd > total_portfolio_usd:
                QMessageBox.warning(
                    self,
                    "Warning",
                    f"Redemption amount (${amount_usd / 1e6:.1f}mm) exceeds "
                    f"portfolio value (${total_portfolio_usd / 1e6:.1f}mm).",
                )
                return

        schedule = compute_schedule(
            self.portfolio,
            self.fund_names,
            amount_usd,
            self.usd_jpy_rate,
            mode,
            direction,
        )

        if not schedule:
            QMessageBox.warning(self, "Warning", "Could not compute schedule.")
            return

        self._schedule = schedule
        self._schedule_direction = direction
        self._schedule_mode = mode
        self._schedule_amount_usd = amount_usd
        self._display_schedule()

    def _display_schedule(self) -> None:
        schedule = self._schedule
        if not schedule:
            return

        # Determine max weeks
        max_weeks = max(len(r["weeks"]) for r in schedule) if schedule else 0

        direction_label = self._schedule_direction.capitalize()
        mode_label = (
            "Maintain Weights" if self._schedule_mode == "maintain_weights"
            else "Minimize Time"
        )
        amount_mm = self._schedule_amount_usd / 1e6

        self._schedule_info_label.setText(
            f"{direction_label}  |  Amount: ${amount_mm:,.1f}mm USD  |  "
            f"Mode: {mode_label}  |  "
            f"Total Weeks: {max_weeks}"
        )

        tbl = self._schedule_table
        tbl.setRowCount(0)

        # Columns: Symbol, Name, Trading Days, Week 1, Week 2, ...
        col_count = 3 + max_weeks
        tbl.setColumnCount(col_count)

        headers = ["Symbol", "Name", "Trading Days"]
        for w in range(1, max_weeks + 1):
            headers.append(f"Week {w}")
        tbl.setHorizontalHeaderLabels(headers)

        tbl.setColumnWidth(0, 80)
        tbl.setColumnWidth(1, 150)
        tbl.setColumnWidth(2, 90)
        for c in range(3, col_count):
            tbl.setColumnWidth(c, 100)

        # Color coding
        sub_color = QColor(198, 239, 206)  # green tint for subscription
        red_color = QColor(255, 199, 206)  # red tint for redemption
        cell_color = sub_color if self._schedule_direction == "subscription" else red_color

        for row_idx, r in enumerate(schedule):
            tbl.insertRow(row_idx)

            sym_item = QTableWidgetItem(r["symbol"])
            sym_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            tbl.setItem(row_idx, 0, sym_item)

            name_item = QTableWidgetItem(r["name"])
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            tbl.setItem(row_idx, 1, name_item)

            td_text = f"{r['trading_days']:.1f}" if r["trading_days"] > 0 else "—"
            td_item = QTableWidgetItem(td_text)
            td_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tbl.setItem(row_idx, 2, td_item)

            for w_idx, w_val in enumerate(r["weeks"]):
                # Show in millions USD
                val_mm = w_val / 1e6
                text = f"${val_mm:,.2f}mm" if val_mm >= 0.01 else f"${w_val:,.0f}"
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setBackground(QBrush(cell_color))
                tbl.setItem(row_idx, 3 + w_idx, item)

            # Fill remaining week columns with empty
            for w_idx in range(len(r["weeks"]), max_weeks):
                empty = QTableWidgetItem("")
                tbl.setItem(row_idx, 3 + w_idx, empty)

    # =====================================================================
    #  PROGRESS HELPERS
    # =====================================================================

    def _make_progress(self, text: str, maximum: int) -> QProgressDialog:
        p = QProgressDialog(text, "Cancel", 0, maximum, self)
        p.setWindowModality(Qt.WindowModal)
        p.setMinimumWidth(400)
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
