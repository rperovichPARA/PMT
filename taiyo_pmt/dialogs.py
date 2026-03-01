"""Reusable dialog windows for Taiyo PMT."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .models import (
    FUND_COLORS_RGB,
    Position,
    ProposedExecution,
    calculate_trade_from_raw,
    filing_thresholds,
    fund_column_index,
    NUM_FIXED_COLUMNS,
)


# ---------------------------------------------------------------------------
# Trade dialog
# ---------------------------------------------------------------------------

class TradeDialog(QDialog):
    """Multi-fund trade proposal dialog with filing threshold alerts."""

    def __init__(
        self,
        parent,
        symbol: str,
        position: Position,
        portfolio: dict[str, Position],
        fund_names: list[str],
        proposed_executions: dict[str, ProposedExecution],
        usd_jpy_rate: float,
        filings: dict | None = None,
        portfolio_table=None,
    ) -> None:
        super().__init__(parent)
        self.symbol = symbol
        self.position = position
        self.portfolio = portfolio
        self.fund_names = fund_names
        self.proposed_executions = proposed_executions
        self.usd_jpy_rate = usd_jpy_rate
        self.filings = filings or {}
        self.portfolio_table = portfolio_table

        self._fund_entries: dict[str, dict] = {}
        self._fund_data: dict[str, dict] = {}
        self._result_trades: dict[str, dict] = {}

        self.setWindowTitle(f"Create Trade for {symbol}")
        self.resize(600, 500)
        self._build_ui()

    @property
    def result_trades(self) -> dict[str, dict]:
        """Trades accepted by the user, keyed by fund name."""
        return self._result_trades

    # ----- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        price = self.position.price
        os_shares = self.position.os_shares

        total_current_shares = self.position.total_quantity
        total_pct = self.position.calculate_pct_of_company()

        pct_up, pct_down = filing_thresholds(
            self.filings.get(self.symbol), total_pct
        )

        # ---- header --------------------------------------------------------
        self._header_widget = QWidget()
        header_layout = QVBoxLayout(self._header_widget)
        header_layout.setContentsMargins(10, 10, 10, 10)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(f"Symbol: {self.symbol}"))
        row1.addWidget(QLabel(f"Name: {self.position.name}"))
        row1.addWidget(QLabel(f"Price: {price:,.2f} JPY"))
        header_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(
            QLabel(f"Current % of Company: {total_pct * 100:.2f}%")
        )
        self._new_pct_label = QLabel("New % of Company: -")
        row2.addWidget(self._new_pct_label)
        self._change_pct_label = QLabel("Change %: -")
        row2.addWidget(self._change_pct_label)
        header_layout.addLayout(row2)

        if pct_up is not None or pct_down is not None:
            row3 = QHBoxLayout()
            if pct_up is not None:
                row3.addWidget(
                    QLabel(f"% to Next Upward: {pct_up * 100:.2f}%")
                )
            if pct_down is not None:
                row3.addWidget(
                    QLabel(f"% to Next Downward: {pct_down * 100:.2f}%")
                )
            header_layout.addLayout(row3)

        layout.addWidget(self._header_widget)

        # ---- per-fund entries -----------------------------------------------
        self._total_current_shares = total_current_shares
        self._total_pct = total_pct
        self._os_shares = os_shares
        self._pct_up = pct_up
        self._pct_down = pct_down

        self._gather_fund_data()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        rgba_colors = [
            f"rgba({r}, {g}, {b}, 0.3)"
            for r, g, b in FUND_COLORS_RGB
        ]

        for fund_idx, fund_name in enumerate(self.fund_names):
            if fund_name not in self._fund_data:
                continue

            fd = self._fund_data[fund_name]
            color = rgba_colors[fund_idx % len(rgba_colors)]

            group = QGroupBox(fund_name)
            group.setStyleSheet(f"QGroupBox {{ background-color: {color}; }}")
            gl = QGridLayout(group)

            gl.addWidget(QLabel("Current Rel. Weight:"), 0, 0)
            gl.addWidget(QLabel(f"{fd['current_raw']:.2f}x"), 0, 1)

            gl.addWidget(QLabel("New Rel. Weight:"), 1, 0)
            raw_input = QDoubleSpinBox()
            raw_input.setRange(0, 10.0)
            raw_input.setDecimals(2)
            raw_input.setSingleStep(0.01)
            raw_input.setValue(fd.get("new_raw", fd["current_raw"]))
            gl.addWidget(raw_input, 1, 1)

            gl.addWidget(QLabel("USD Value:"), 1, 2)
            usd_display = QLabel("")
            gl.addWidget(usd_display, 1, 3)

            gl.addWidget(QLabel("Trade Type:"), 2, 0)
            type_label = QLabel("")
            gl.addWidget(type_label, 2, 1)

            gl.addWidget(QLabel("Shares:"), 2, 2)
            shares_label = QLabel("")
            gl.addWidget(shares_label, 2, 3)

            self._fund_entries[fund_name] = {
                "raw_input": raw_input,
                "usd_display": usd_display,
                "trade_type_label": type_label,
                "shares_label": shares_label,
            }

            def _make_handler(fn):
                return lambda _val: self._on_raw_changed(fn)

            raw_input.valueChanged.connect(_make_handler(fund_name))
            scroll_layout.addWidget(group)

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # ---- buttons --------------------------------------------------------
        btn_layout = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_layout.addWidget(cancel)
        btn_layout.addStretch()
        submit = QPushButton("Submit")
        submit.clicked.connect(self._on_submit)
        btn_layout.addWidget(submit)
        layout.addLayout(btn_layout)

        # Trigger initial calculations for existing trades
        for fund_name in self._fund_entries:
            fd = self._fund_data[fund_name]
            if abs(fd.get("new_raw", fd["current_raw"]) - fd["current_raw"]) > 0.001:
                self._on_raw_changed(fund_name)

        self._update_company_pct()

    def _gather_fund_data(self) -> None:
        """Read current/new RAW values from the portfolio table."""
        for fund_idx, fund_name in enumerate(self.fund_names):
            rel_col = fund_column_index(fund_idx, 0)
            new_col = fund_column_index(fund_idx, 1)

            rel_weight_value = None
            new_weight_value = None

            if self.portfolio_table is not None:
                for row in range(self.portfolio_table.rowCount()):
                    item = self.portfolio_table.item(row, 1)
                    if item and item.text() == self.symbol:
                        rw_item = self.portfolio_table.item(row, rel_col)
                        if rw_item and rw_item.text():
                            try:
                                rel_weight_value = float(
                                    rw_item.text().replace("x", "")
                                )
                            except ValueError:
                                pass

                        nw_item = self.portfolio_table.item(row, new_col)
                        if nw_item and nw_item.text():
                            try:
                                new_weight_value = float(
                                    nw_item.text().replace("x", "")
                                )
                            except ValueError:
                                pass
                        break

            if rel_weight_value is None:
                continue

            entry = {
                "current_raw": rel_weight_value,
                "new_raw": (
                    new_weight_value
                    if new_weight_value is not None and new_weight_value > 0
                    else rel_weight_value
                ),
            }

            fp = self.position.funds.get(fund_name)
            if fp is not None:
                entry["quantity"] = fp.quantity

            # Check existing proposed execution
            key = f"{fund_name}:{self.symbol}"
            if key in self.proposed_executions:
                entry["new_raw"] = self.proposed_executions[key].target_raw

            self._fund_data[fund_name] = entry

    # ----- callbacks ---------------------------------------------------------

    def _on_raw_changed(self, fund_name: str) -> None:
        fd = self._fund_data[fund_name]
        entries = self._fund_entries[fund_name]
        current_raw = fd["current_raw"]
        new_raw = entries["raw_input"].value()

        if abs(new_raw - current_raw) < 0.001:
            for key in ("usd_display", "shares_label", "trade_type_label"):
                entries[key].setText("")
                entries[key].setStyleSheet("")
            self._update_company_pct()
            return

        result = calculate_trade_from_raw(
            self.portfolio, fund_name, self.symbol, new_raw, self.usd_jpy_rate
        )
        if result is None:
            return

        entries["usd_display"].setText(f"{abs(int(result['trade_value_usd'])):,} USD")

        if abs(result["trade_quantity"]) > 0:
            entries["shares_label"].setText(f"{result['trade_quantity']:,}")
            entries["trade_type_label"].setText(result["trade_type"])
            color = "green" if result["trade_type"] == "Buy" else "red"
            for key in ("trade_type_label", "shares_label", "usd_display"):
                entries[key].setStyleSheet(f"color: {color};")
        else:
            for key in ("usd_display", "shares_label", "trade_type_label"):
                entries[key].setText("")
                entries[key].setStyleSheet("")

        self._update_company_pct()

    def _update_company_pct(self) -> None:
        if self._os_shares <= 0:
            return

        net_shares = 0
        for fund_name, entries in self._fund_entries.items():
            text = entries["shares_label"].text().replace(",", "")
            if text:
                try:
                    net_shares += int(text)
                except ValueError:
                    pass

        new_total = self._total_current_shares + net_shares
        new_pct = new_total / self._os_shares if self._os_shares > 0 else 0
        pct_change = new_pct - self._total_pct

        self._new_pct_label.setText(f"New % of Company: {new_pct * 100:.2f}%")
        self._change_pct_label.setText(f"Change %: {pct_change * 100:+.2f}%")

        if pct_change > 0:
            self._change_pct_label.setStyleSheet("color: green;")
        elif pct_change < 0:
            self._change_pct_label.setStyleSheet("color: red;")
        else:
            self._change_pct_label.setStyleSheet("")

        filing_alert = False
        if self._pct_up is not None and pct_change >= self._pct_up:
            filing_alert = True
        if self._pct_down is not None and pct_change <= -self._pct_down:
            filing_alert = True

        self._header_widget.setStyleSheet(
            "background-color: #FFFFC0;" if filing_alert else ""
        )

    def _on_submit(self) -> None:
        for fund_name, entries in self._fund_entries.items():
            trade_type = entries["trade_type_label"].text()
            if not trade_type:
                continue

            shares_text = entries["shares_label"].text().replace(",", "")
            usd_text = (
                entries["usd_display"].text().replace(",", "").replace(" USD", "")
            )

            try:
                trade_quantity = float(shares_text) if shares_text else 0
                trade_value_usd = float(usd_text) if usd_text else 0
            except ValueError:
                continue

            if trade_quantity == 0 or trade_value_usd == 0:
                continue

            self._result_trades[fund_name] = {
                "trade_type": trade_type,
                "target_raw": entries["raw_input"].value(),
                "trade_quantity": trade_quantity,
                "trade_value_usd": trade_value_usd,
            }

        self.accept()


# ---------------------------------------------------------------------------
# Target-price edit dialog
# ---------------------------------------------------------------------------

class TargetPriceDialog(QDialog):
    """Small dialog for editing the target price of a proposed trade."""

    def __init__(self, parent, symbol: str, current_price: float, current_target: float = 0):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Target Price for {symbol}")
        self.resize(350, 150)

        self.target_price: int | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Current Price: {current_price:,.2f} JPY"))

        row = QHBoxLayout()
        row.addWidget(QLabel("Target Price:"))
        self._spin = QSpinBox()
        self._spin.setRange(0, 1_000_000)
        self._spin.setSingleStep(100)
        if current_target:
            self._spin.setValue(int(current_target))
        row.addWidget(self._spin)
        layout.addLayout(row)

        btns = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        btns.addStretch()
        update = QPushButton("Update")
        update.clicked.connect(self._on_update)
        btns.addWidget(update)
        layout.addLayout(btns)

    def _on_update(self) -> None:
        self.target_price = self._spin.value()
        if self.target_price <= 0:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", "Target Price must be positive")
            return
        self.accept()


# ---------------------------------------------------------------------------
# Add-position dialog
# ---------------------------------------------------------------------------

class AddPositionDialog(QDialog):
    """Dialog for manually adding a new portfolio position."""

    def __init__(self, parent, fund_names: list[str], usd_jpy_rate: float):
        super().__init__(parent)
        self.fund_names = fund_names or ["Default"]
        self.usd_jpy_rate = usd_jpy_rate

        self.result_position: Position | None = None
        self.result_fund_quantities: dict[str, float] = {}

        self.setWindowTitle("Add New Position")
        self.resize(400, 350)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QGridLayout()

        form.addWidget(QLabel("Symbol:"), 0, 0)
        self._symbol_input = QLineEdit()
        form.addWidget(self._symbol_input, 0, 1)

        form.addWidget(QLabel("Name:"), 1, 0)
        self._name_input = QLineEdit()
        form.addWidget(self._name_input, 1, 1)

        form.addWidget(QLabel("Current Price (JPY):"), 2, 0)
        self._price_input = QLineEdit()
        form.addWidget(self._price_input, 2, 1)

        form.addWidget(QLabel("10% 3m ADV (USD):"), 3, 0)
        self._adv_input = QLineEdit("0")
        form.addWidget(self._adv_input, 3, 1)

        self._cash_check = QCheckBox("This is a cash position")
        self._cash_check.stateChanged.connect(self._on_cash_toggled)
        form.addWidget(self._cash_check, 4, 0, 1, 2)

        currency_group = QGroupBox()
        cl = QHBoxLayout(currency_group)
        self._currency_group = QButtonGroup(self)
        self._jpy_radio = QRadioButton("JPY")
        self._jpy_radio.setChecked(True)
        self._usd_radio = QRadioButton("USD")
        self._currency_group.addButton(self._jpy_radio)
        self._currency_group.addButton(self._usd_radio)
        cl.addWidget(self._jpy_radio)
        cl.addWidget(self._usd_radio)
        form.addWidget(currency_group, 5, 0, 1, 2)

        layout.addLayout(form)

        # Fund quantities
        fund_group = QGroupBox("Select Funds")
        fl = QVBoxLayout(fund_group)
        self._fund_checks: dict[str, QCheckBox] = {}
        self._fund_qty_inputs: dict[str, QSpinBox] = {}

        for fn in self.fund_names:
            row = QHBoxLayout()
            chk = QCheckBox(fn)
            chk.setChecked(True)
            row.addWidget(chk)
            self._fund_checks[fn] = chk

            row.addWidget(QLabel("Quantity:"))
            qty = QSpinBox()
            qty.setRange(0, 100_000_000)
            qty.setSingleStep(100)
            row.addWidget(qty)
            self._fund_qty_inputs[fn] = qty
            fl.addLayout(row)

        layout.addWidget(fund_group)

        btns = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        btns.addStretch()
        add = QPushButton("Add")
        add.clicked.connect(self._on_add)
        btns.addWidget(add)
        layout.addLayout(btns)

    def _on_cash_toggled(self, state) -> None:
        from PyQt5.QtCore import Qt

        if state == Qt.Checked:
            self._symbol_input.setText("JPY")
            self._name_input.setText("Japanese Yen")
            self._price_input.setText("1.0")
        else:
            self._symbol_input.clear()
            self._name_input.clear()
            self._price_input.clear()

    def _on_add(self) -> None:
        from PyQt5.QtWidgets import QMessageBox

        symbol = self._symbol_input.text().strip()
        name = self._name_input.text().strip()
        if not symbol:
            QMessageBox.critical(self, "Error", "Symbol is required")
            return
        if not name:
            QMessageBox.critical(self, "Error", "Name is required")
            return

        try:
            price = float(self._price_input.text())
            if price <= 0:
                raise ValueError
        except (ValueError, TypeError):
            QMessageBox.critical(self, "Error", "Price must be a positive number")
            return

        try:
            adv = float(self._adv_input.text()) if self._adv_input.text() else 0
        except ValueError:
            QMessageBox.critical(self, "Error", "ADV must be a number")
            return

        is_cash = self._cash_check.isChecked()
        currency = "JPY" if self._jpy_radio.isChecked() else "USD"

        fund_qtys: dict[str, float] = {}
        for fn, chk in self._fund_checks.items():
            if chk.isChecked():
                qty = self._fund_qty_inputs[fn].value()
                if qty <= 0:
                    QMessageBox.critical(
                        self, "Error", f"Quantity for {fn} must be positive"
                    )
                    return
                fund_qtys[fn] = qty

        if not fund_qtys:
            QMessageBox.critical(
                self, "Error", "Select at least one fund with a quantity"
            )
            return

        if is_cash:
            symbol = currency
            name = "Japanese Yen" if currency == "JPY" else "US Dollar"
            price = 1.0 if currency == "JPY" else self.usd_jpy_rate

        self.result_position = Position(
            symbol=symbol,
            name=name,
            price=price,
            is_cash=is_cash,
            adv_10pct=adv,
            currency=currency if is_cash else "JPY",
        )
        self.result_fund_quantities = fund_qtys
        self.accept()
