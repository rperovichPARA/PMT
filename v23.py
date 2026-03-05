import sys
import os
import pandas as pd
from datetime import datetime
import threading
import math
import numpy as np
import re
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt6gg import FigureCanvasQTAgg as FigureCanvas
import yfinance as yf
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QTabWidget, QTableWidget,
                             QHeaderView, QTableWidgetItem, QFrame, QGridLayout, QFileDialog,
                             QProgressDialog, QMessageBox, QSplitter, QCheckBox,
                             QComboBox, QRadioButton, QButtonGroup, QDialog, QGroupBox,
                             QScrollArea, QSpacerItem, QSizePolicy, QSpinBox, QDoubleSpinBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QBrush


class PortfolioManager(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Taiyo PMT Trading V2")
        self.resize(1400, 700)

        # Store portfolio data
        self.portfolio = {}
        self.usd_jpy_rate = 0.0
        self.funds = {}  # Store data by fund
        self.fund_names = []  # List of fund names

        # Store filings data
        self.filings = {}  # Store filings by symbol
        self.filings_visible = False  # Flag for filings frame visibility

        # Sorting state
        self.sort_column = ""
        self.sort_reverse = False
        self.auto_sort_enabled = True  # Flag to control automatic sorting

        # Store proposed executions
        self.proposed_executions = {}

        # Flag for chart visibility
        self.chart_visible = False

        # Price source flag
        self.use_yfinance_pricing = False  # Default to use Excel prices

        # Add a flag to track if we've imported trades
        self.has_imported_trades = False

        # Font size tracking - default to 9pt
        self.current_font_size = 9
        self.min_font_size = 7
        self.max_font_size = 14

        # Create main layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Create main vertical layout
        main_layout = QVBoxLayout(self.central_widget)

        # Create font size controls at the top
        self.create_font_controls(main_layout)

        # Create menu bar with options
        self.create_menu_bar()

        # Create horizontal splitter for portfolio/trades
        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # Left panel (portfolio and position details)
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)

        # Portfolio table
        self.create_portfolio_frame(left_layout)

        # Position details frame
        self.create_position_frame(left_layout)

        self.main_splitter.addWidget(self.left_panel)

        # Middle panel (filings - initially hidden)
        self.middle_panel = QWidget()
        middle_layout = QVBoxLayout(self.middle_panel)
        self.create_filings_frame(middle_layout)
        self.middle_panel.setVisible(False)  # Hidden initially
        self.main_splitter.addWidget(self.middle_panel)

        # Right panel (proposed trades)
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)

        # Proposed trades table and controls
        self.create_proposed_trades_frame(right_layout)

        self.main_splitter.addWidget(self.right_panel)

        # Set the initial splitter sizes (75% left, 25% right)
        self.main_splitter.setSizes([1050, 0, 350])  # Middle panel size is 0 (hidden)

        # Apply initial font settings
        self.update_application_fonts()

        # Initial update of exchange rate
        self.update_exchange_rate()

    def create_cash_path_chart(self):
        """Create the cash path charts for each fund - with improved layout and space utilization"""
        # Clear existing charts
        for i in reversed(range(self.chart_layout.count())):
            self.chart_layout.itemAt(i).widget().deleteLater()

        if not self.proposed_executions:
            # No trades to chart
            self.chart_layout.addWidget(QLabel("No proposed trades to chart"))
            return

        try:
            # Process executions by fund
            fund_executions = {}

            for key, execution in self.proposed_executions.items():
                if ':' in key:
                    fund_name, symbol = key.split(':', 1)

                    if fund_name not in fund_executions:
                        fund_executions[fund_name] = []

                    fund_executions[fund_name].append({
                        'symbol': symbol,
                        'execution': execution
                    })

            # If no fund has executions, return
            if not fund_executions:
                self.chart_layout.addWidget(QLabel("No fund-specific trades to chart"))
                return

            # Create a scroll area for the charts
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)

            # Create a container widget for the scroll area
            scroll_widget = QWidget()
            scroll_layout = QVBoxLayout(scroll_widget)
            scroll_layout.setContentsMargins(6, 6, 6, 6)  # Reduced margins
            scroll_layout.setSpacing(8)  # Reduced spacing between fund charts

            # For each fund, create a chart
            for fund_name, executions in fund_executions.items():
                # Skip if no executions for this fund
                if not executions:
                    continue

                try:
                    # Create a group box for this fund's chart with a more compact layout
                    fund_group = QGroupBox(f"Cash Path for {fund_name}")
                    fund_layout = QVBoxLayout(fund_group)
                    fund_layout.setContentsMargins(5, 5, 5, 5)  # Reduced margins
                    fund_layout.setSpacing(0)  # Minimal spacing between elements

                    # Calculate max days needed for x-axis - limit to a reasonable number
                    max_days = 0
                    for item in executions:
                        execution = item['execution']
                        if 'trading_days' in execution and execution['trading_days']:
                            max_days = max(max_days, min(math.ceil(execution['trading_days']), 30))  # Limit to 30 days

                    if max_days == 0:
                        fund_layout.addWidget(QLabel(f"No trading days information available for {fund_name}"))
                        scroll_layout.addWidget(fund_group)
                        continue

                    # Get fund-specific cash position
                    initial_cash_usd = self.get_fund_cash_usd(fund_name)

                    try:
                        # Create the chart for this fund
                        fund_chart_widget, current_cash, min_cash, ending_cash = self.create_fund_cash_path_chart(
                            fund_name, executions.copy(), max_days, initial_cash_usd)

                        # Calculate net change
                        net_change = ending_cash - current_cash

                        # Create a SINGLE LINE with all cash position values - much more compact
                        cash_info = QLabel(
                            f"Current: ${current_cash:.2f}mm    Minimum: ${min_cash:.2f}mm    Ending: ${ending_cash:.2f}mm    "
                            f"Net Change: <span style='color: {'green' if net_change > 0 else 'red'};'>${net_change:.2f}mm</span>"
                        )
                        cash_info.setAlignment(Qt.AlignLeft)
                        cash_info.setTextFormat(Qt.RichText)

                        # Make font slightly smaller for the cash info line
                        info_font = cash_info.font()
                        info_font.setPointSize(
                            max(self.current_font_size - 1, 7))  # Slightly smaller than current font size, min 7pt
                        cash_info.setFont(info_font)

                        # Add minimal height for cash info
                        cash_info.setMaximumHeight(self.current_font_size * 2)

                        # Add the info and chart to the fund layout with minimal spacing
                        fund_layout.addWidget(cash_info)
                        fund_layout.addWidget(fund_chart_widget)

                        # Set size policy to expand the chart vertically
                        fund_chart_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

                    except Exception as chart_error:
                        # If chart creation fails, show error message
                        error_widget = QLabel(f"Error creating chart for {fund_name}: {str(chart_error)}")
                        error_widget.setStyleSheet("color: red;")
                        fund_layout.addWidget(error_widget)
                        print(f"Chart creation error: {str(chart_error)}")
                        import traceback
                        traceback.print_exc()

                    # Add to scroll area regardless of chart success
                    scroll_layout.addWidget(fund_group)

                except Exception as fund_error:
                    # If entire fund section fails, add error message to scroll layout
                    error_label = QLabel(f"Error processing fund {fund_name}: {str(fund_error)}")
                    error_label.setStyleSheet("color: red;")
                    scroll_layout.addWidget(error_label)
                    print(f"Fund processing error: {str(fund_error)}")
                    import traceback
                    traceback.print_exc()

            # Add the scroll widget to the scroll area
            scroll_area.setWidget(scroll_widget)
            self.chart_layout.addWidget(scroll_area)

        except Exception as e:
            # Global error handler
            error_label = QLabel(f"Error creating cash path charts: {str(e)}")
            error_label.setStyleSheet("color: red;")
            self.chart_layout.addWidget(error_label)
            print(f"Global chart error: {str(e)}")
            import traceback
            traceback.print_exc()

    def create_font_controls(self, parent_layout):
        """Create font size adjustment controls at the top of the application"""
        font_control_layout = QHBoxLayout()

        # Add spacer to push controls to the right
        font_control_layout.addStretch()

        # Font size label
        self.font_size_label = QLabel(f"Font Size: {self.current_font_size}pt")

        # Minus button
        minus_btn = QPushButton("-")
        minus_btn.setFixedWidth(30)  # Make buttons square and small
        minus_btn.setToolTip("Decrease font size")
        minus_btn.clicked.connect(self.decrease_font_size)

        # Plus button
        plus_btn = QPushButton("+")
        plus_btn.setFixedWidth(30)  # Make buttons square and small
        plus_btn.setToolTip("Increase font size")
        plus_btn.clicked.connect(self.increase_font_size)

        # Add controls to layout
        font_control_layout.addWidget(minus_btn)
        font_control_layout.addWidget(self.font_size_label)
        font_control_layout.addWidget(plus_btn)

        # Add layout to parent
        parent_layout.addLayout(font_control_layout)

    def increase_font_size(self):
        """Increase the font size by 1pt"""
        if self.current_font_size < self.max_font_size:
            self.current_font_size += 1
            self.update_application_fonts()

    def decrease_font_size(self):
        """Decrease the font size by 1pt"""
        if self.current_font_size > self.min_font_size:
            self.current_font_size -= 1
            self.update_application_fonts()

    def update_application_fonts(self):
        """Update fonts throughout the application based on current_font_size"""
        # Update font size label
        self.font_size_label.setText(f"Font Size: {self.current_font_size}pt")

        # Create base font with the current size
        base_font = QFont()
        base_font.setPointSize(self.current_font_size)

        # Create a bold version for headers
        bold_font = QFont(base_font)
        bold_font.setBold(True)

        # Apply to application
        QApplication.setFont(base_font)

        # Apply to all tables - fix the incorrect table.__name__ reference
        tables = []
        if hasattr(self, 'portfolio_table') and self.portfolio_table is not None:
            tables.append(self.portfolio_table)
        if hasattr(self, 'header_table') and self.header_table is not None:
            tables.append(self.header_table)
        if hasattr(self, 'filings_table') and self.filings_table is not None:
            tables.append(self.filings_table)
        if hasattr(self, 'proposed_trades_table') and self.proposed_trades_table is not None:
            tables.append(self.proposed_trades_table)

        for table in tables:
            table.setFont(base_font)
            # Apply bold font to headers
            header_font = bold_font
            header_font.setPointSize(self.current_font_size)
            table.horizontalHeader().setFont(header_font)

        # Update table row heights based on font size
        row_height = self.current_font_size * 2 + 10  # Scale row height with font size

        # Apply to portfolio table
        if hasattr(self, 'portfolio_table') and self.portfolio_table is not None:
            for row in range(self.portfolio_table.rowCount()):
                self.portfolio_table.setRowHeight(row, row_height)

        # Apply to filings table
        if hasattr(self, 'filings_table') and self.filings_table is not None:
            for row in range(self.filings_table.rowCount()):
                self.filings_table.setRowHeight(row, row_height)

        # Apply to proposed trades table
        if hasattr(self, 'proposed_trades_table') and self.proposed_trades_table is not None:
            for row in range(self.proposed_trades_table.rowCount()):
                self.proposed_trades_table.setRowHeight(row, row_height)

        # Apply to header table
        if hasattr(self, 'header_table') and self.header_table is not None:
            self.header_table.setRowHeight(0, row_height)

        # Apply to position details labels
        position_labels = []
        for label_name in [
            'symbol_label', 'name_label', 'price_label', 'quantity_label',
            'value_jpy_label', 'value_usd_label', 'weight_label', 'rel_weight_label',
            'exchange_rate_label', 'total_usd_label'
        ]:
            if hasattr(self, label_name) and getattr(self, label_name) is not None:
                position_labels.append(getattr(self, label_name))

        label_font = QFont(base_font)
        for label in position_labels:
            label.setFont(label_font)

        # Update table column widths based on font size
        if hasattr(self, 'refresh_portfolio_display'):
            # Refresh the portfolio display to update column widths
            self.refresh_portfolio_display()

        # Update table header heights
        header_height = self.current_font_size * 2 + 6  # Slightly smaller than row height

        if hasattr(self, 'portfolio_table') and self.portfolio_table is not None:
            self.portfolio_table.horizontalHeader().setFixedHeight(header_height)

        if hasattr(self, 'filings_table') and self.filings_table is not None:
            self.filings_table.horizontalHeader().setFixedHeight(header_height)

        if hasattr(self, 'proposed_trades_table') and self.proposed_trades_table is not None:
            self.proposed_trades_table.horizontalHeader().setFixedHeight(header_height)

    def create_menu_bar(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu('File')

        import_action = file_menu.addAction('Import Portfolio')
        import_action.triggered.connect(self.import_portfolio)

        export_action = file_menu.addAction('Export Proposed Trades')
        export_action.triggered.connect(self.export_proposed_trades)

        file_menu.addSeparator()

        exit_action = file_menu.addAction('Exit')
        exit_action.triggered.connect(self.close)

        # Settings menu
        settings_menu = menubar.addMenu('Settings')

        # Price source submenu
        price_menu = settings_menu.addMenu('Price Source')

        self.excel_price_action = price_menu.addAction('Use Excel Prices')
        self.excel_price_action.setCheckable(True)
        self.excel_price_action.setChecked(True)
        self.excel_price_action.triggered.connect(self.set_excel_prices)

        self.yfinance_price_action = price_menu.addAction('Use YFinance Prices')
        self.yfinance_price_action.setCheckable(True)
        self.yfinance_price_action.triggered.connect(self.set_yfinance_prices)

    def set_excel_prices(self):
        if not self.excel_price_action.isChecked():
            self.excel_price_action.setChecked(True)
            return

        self.use_yfinance_pricing = False
        self.yfinance_price_action.setChecked(False)
        QMessageBox.information(self, "Price Source", "Using prices from Excel file")

    def set_yfinance_prices(self):
        if not self.yfinance_price_action.isChecked():
            self.yfinance_price_action.setChecked(True)
            return

        self.use_yfinance_pricing = True
        self.excel_price_action.setChecked(False)

        # Ask if user wants to refresh all prices now
        reply = QMessageBox.question(self, "Refresh Prices",
                                     "Do you want to refresh all prices from YFinance now?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.refresh_prices()

    def create_portfolio_frame(self, parent_layout):
        """Create the portfolio frame with a header table and main table"""
        # Group box for portfolio section
        portfolio_group = QGroupBox("Portfolio")
        self.portfolio_group = portfolio_group
        portfolio_layout = QVBoxLayout(portfolio_group)

        # Top button bar
        top_button_layout = QHBoxLayout()

        # Import button
        import_btn = QPushButton("Import Portfolio")
        import_btn.clicked.connect(self.import_portfolio)
        top_button_layout.addWidget(import_btn)

        # Import Trades button - Added NEW button here
        import_trades_btn = QPushButton("Import Trades")
        import_trades_btn.clicked.connect(self.import_trades)
        top_button_layout.addWidget(import_trades_btn)

        # Import Filings button
        import_filings_btn = QPushButton("Import Filings")
        import_filings_btn.clicked.connect(self.import_filings)
        top_button_layout.addWidget(import_filings_btn)

        # Show Filings button
        show_filings_btn = QPushButton("Show Filings")
        show_filings_btn.clicked.connect(self.toggle_filings_frame)
        top_button_layout.addWidget(show_filings_btn)

        # Add spacer to push create trade button to the right
        top_button_layout.addStretch()

        # Create trade button (right-aligned)
        create_trade_btn = QPushButton("Create Trade")
        create_trade_btn.clicked.connect(self.create_trade_dialog)
        top_button_layout.addWidget(create_trade_btn)

        portfolio_layout.addLayout(top_button_layout)

        # Create a container widget for the header and table
        table_container = QWidget()
        container_layout = QVBoxLayout(table_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Create header table - will display fund names
        self.header_table = QTableWidget(1, 0)  # 1 row, columns will be set dynamically
        self.header_table.setMaximumHeight(25)  # Fixed height for header
        self.header_table.horizontalHeader().setVisible(False)  # Hide header of header table
        self.header_table.verticalHeader().setVisible(False)  # Hide vertical header
        self.header_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.header_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Regular portfolio table
        self.portfolio_table = QTableWidget()
        self.portfolio_table.setAlternatingRowColors(True)
        self.portfolio_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.portfolio_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.portfolio_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.portfolio_table.horizontalHeader().setStretchLastSection(False)
        self.portfolio_table.verticalHeader().setVisible(False)

        # Remove vertical dividers in table
        self.portfolio_table.setStyleSheet("""
            QTableWidget::item {
                border-right: 0px;
                padding: 6px;
            }
            QHeaderView::section {
                border-right: 0px;
            }
        """)

        # Connect the cell click event to selection handler
        self.portfolio_table.itemSelectionChanged.connect(self.on_position_select)

        # Connect double-click to open trade dialog
        self.portfolio_table.cellDoubleClicked.connect(self.on_portfolio_double_click)

        # Connect header click for sorting
        self.portfolio_table.horizontalHeader().sectionClicked.connect(self.sort_portfolio_table)

        # Synchronize scrolling between header table and main table
        self.portfolio_table.horizontalScrollBar().valueChanged.connect(
            self.header_table.horizontalScrollBar().setValue)

        # Add tables to container
        container_layout.addWidget(self.header_table)
        container_layout.addWidget(self.portfolio_table)

        # Add container to layout
        portfolio_layout.addWidget(table_container)

        # Bottom button bar
        bottom_button_layout = QHBoxLayout()

        # Add position button
        add_position_btn = QPushButton("Add Position")
        add_position_btn.clicked.connect(self.add_position_dialog)
        bottom_button_layout.addWidget(add_position_btn)

        # Remove position button
        remove_position_btn = QPushButton("Remove Position")
        remove_position_btn.clicked.connect(self.remove_position)
        bottom_button_layout.addWidget(remove_position_btn)

        # Refresh prices button
        refresh_btn = QPushButton("Refresh Prices")
        refresh_btn.clicked.connect(self.refresh_prices)
        bottom_button_layout.addWidget(refresh_btn)

        # Clear trades button
        clear_btn = QPushButton("Clear All Proposed Trades")
        clear_btn.clicked.connect(self.clear_proposed_executions)
        bottom_button_layout.addWidget(clear_btn)

        # Add spacer
        bottom_button_layout.addStretch()

        # Exchange rate display
        self.exchange_rate_label = QLabel("USD/JPY: Loading...")
        bottom_button_layout.addWidget(self.exchange_rate_label)

        portfolio_layout.addLayout(bottom_button_layout)

        # Add the portfolio frame to the parent layout
        parent_layout.addWidget(portfolio_group)

    def create_filings_frame(self, parent_layout):
        """Create the filings frame with a table for showing filing information"""
        # Group box for filings section
        filings_group = QGroupBox("Filings Information")
        filings_layout = QVBoxLayout(filings_group)

        # Top controls
        top_layout = QHBoxLayout()

        # Add spacer to push the hide button to the right
        top_layout.addStretch()

        # Hide button (right-aligned)
        hide_filings_btn = QPushButton("Hide Filings")
        hide_filings_btn.clicked.connect(self.toggle_filings_frame)
        top_layout.addWidget(hide_filings_btn)

        filings_layout.addLayout(top_layout)

        # Filings table
        self.filings_table = QTableWidget()
        self.filings_table.setAlternatingRowColors(True)
        self.filings_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.filings_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.filings_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.filings_table.horizontalHeader().setStretchLastSection(False)
        self.filings_table.verticalHeader().setVisible(False)

        # Set up columns
        columns = ["Symbol", "Name", "Date", "Last Filing", "% to Next Upward", "% to Next Downward"]
        self.filings_table.setColumnCount(len(columns))
        self.filings_table.setHorizontalHeaderLabels(columns)

        # Set column widths
        self.filings_table.setColumnWidth(0, 80)  # Symbol
        self.filings_table.setColumnWidth(1, 150)  # Name
        self.filings_table.setColumnWidth(2, 100)  # Date
        self.filings_table.setColumnWidth(3, 100)  # Last Filing
        self.filings_table.setColumnWidth(4, 130)  # % to Next Upward
        self.filings_table.setColumnWidth(5, 130)  # % to Next Downward

        # Remove vertical dividers in table
        self.filings_table.setStyleSheet("""
            QTableWidget::item {
                border-right: 0px;
                padding: 6px;
            }
            QHeaderView::section {
                border-right: 0px;
            }
        """)

        # Connect header click for sorting
        self.filings_table.horizontalHeader().sectionClicked.connect(self.sort_filings_table)

        filings_layout.addWidget(self.filings_table)

        # Add the filings frame to the parent layout
        parent_layout.addWidget(filings_group)

    def on_filings_import_completed(self, filings):
        """Handle completed filings import"""
        # Store the filings data
        self.filings = filings

        # Refresh the filings display
        self.refresh_filings_display()

        # If filings frame is not visible, show it
        if not self.filings_visible:
            self.toggle_filings_frame()

        # Show a success message
        QMessageBox.information(self, "Import Successful", f"Successfully imported {len(filings)} filing records")

    def refresh_filings_display(self):
        """Refresh the filings display table with debug information"""
        # Clear table
        self.filings_table.setRowCount(0)

        # If no filings, return
        if not self.filings:
            return

        # Debug information - print portfolio data
        print("DEBUG - Portfolio Data:")
        for symbol, position in self.portfolio.items():
            total_pct = position.get('total_pct_of_company', 'N/A')
            print(f"Symbol: {symbol}, Total % of Company: {total_pct}")

        # Set row height based on font size
        row_height = self.current_font_size * 2 + 10

        # Adjust column widths based on font size
        font_scaling_factor = self.current_font_size / 9.0  # Scale relative to default font size

        # Set column widths
        self.filings_table.setColumnWidth(0, int(80 * font_scaling_factor))  # Symbol
        self.filings_table.setColumnWidth(1, int(150 * font_scaling_factor))  # Name
        self.filings_table.setColumnWidth(2, int(100 * font_scaling_factor))  # Date
        self.filings_table.setColumnWidth(3, int(100 * font_scaling_factor))  # Last Filing
        self.filings_table.setColumnWidth(4, int(130 * font_scaling_factor))  # % to Next Upward
        self.filings_table.setColumnWidth(5, int(130 * font_scaling_factor))  # % to Next Downward

        # Add rows to table
        row = 0
        for symbol, filing_data in self.filings.items():
            self.filings_table.insertRow(row)

            # Set row height based on font size
            self.filings_table.setRowHeight(row, row_height)

            # Symbol
            symbol_item = QTableWidgetItem(symbol)
            self.filings_table.setItem(row, 0, symbol_item)

            # Name
            name_item = QTableWidgetItem(filing_data['name'])
            self.filings_table.setItem(row, 1, name_item)

            # Date
            date_item = QTableWidgetItem(filing_data['date'] if filing_data['date'] else "")
            self.filings_table.setItem(row, 2, date_item)

            # Last Filing - get the value as a decimal (e.g., 0.0543 for 5.43%)
            last_filing = filing_data['last_filing']

            # Debug
            print(f"DEBUG - Symbol: {symbol}, Last Filing: {last_filing}")

            last_filing_str = f"{last_filing * 100:.2f}%" if last_filing is not None else ""
            last_filing_item = QTableWidgetItem(last_filing_str)
            last_filing_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.filings_table.setItem(row, 3, last_filing_item)

            # Get current % of company from portfolio data
            current_pct = None
            if symbol in self.portfolio:
                current_pct = self.portfolio[symbol].get('total_pct_of_company')

                # Debug
                print(f"DEBUG - Symbol: {symbol}, Current % from portfolio: {current_pct}")

                # If current_pct is None or zero but we have portfolio data, try to calculate it
                if (current_pct is None or current_pct == 0) and 'os_shares' in self.portfolio[symbol]:
                    os_shares = self.portfolio[symbol]['os_shares']
                    if os_shares > 0:
                        # Calculate total shares across all funds
                        total_shares = 0
                        for fund_name, fund_position in self.portfolio[symbol]['funds'].items():
                            total_shares += fund_position['quantity']

                        # Calculate % of company
                        current_pct = total_shares / os_shares

                        # Debug
                        print(f"DEBUG - Symbol: {symbol}, Calculated %: {current_pct}")

            # % to Next Upward - calculate regardless of last_filing value
            pct_upward_str = ""
            if current_pct is not None:
                if last_filing is not None:
                    # Formula: (Last Filing + 1%) - Current %
                    pct_upward = (last_filing + 0.01) - current_pct
                    # Debug
                    print(f"DEBUG - Symbol: {symbol}, Formula: ({last_filing} + 0.01) - {current_pct} = {pct_upward}")
                else:
                    # If no Last Filing, use: 5% - Current %
                    pct_upward = 0.05 - current_pct
                    # Debug
                    print(f"DEBUG - Symbol: {symbol}, No filing formula: 0.05 - {current_pct} = {pct_upward}")

                # Format with 2 decimal places
                pct_upward_str = f"{pct_upward * 100:.2f}%"

            upward_item = QTableWidgetItem(pct_upward_str)
            upward_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.filings_table.setItem(row, 4, upward_item)

            # % to Next Downward - only calculate if we have a Last Filing value
            pct_downward_str = ""
            if current_pct is not None and last_filing is not None:
                # Formula: Current % - (Last Filing - 1%)
                pct_downward = current_pct - (last_filing - 0.01)
                # Debug
                print(
                    f"DEBUG - Symbol: {symbol}, Downward formula: {current_pct} - ({last_filing} - 0.01) = {pct_downward}")

                # Format with 2 decimal places
                pct_downward_str = f"{pct_downward * 100:.2f}%"

            downward_item = QTableWidgetItem(pct_downward_str)
            downward_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.filings_table.setItem(row, 5, downward_item)

            # Color code the cells based on values
            if pct_upward_str:
                try:
                    pct_upward_value = float(pct_upward_str.replace("%", ""))
                    # Format: positive values (approaching upward threshold) in orange, negative in green
                    if pct_upward_value > 0:
                        upward_item.setBackground(QBrush(QColor(255, 235, 156)))  # Light orange
                    else:
                        upward_item.setBackground(QBrush(QColor(198, 239, 206)))  # Light green
                except ValueError:
                    pass  # Skip coloring if conversion fails

            if pct_downward_str:
                try:
                    pct_downward_value = float(pct_downward_str.replace("%", ""))
                    # Format: positive values (far from downward threshold) in green, negative in red
                    if pct_downward_value > 0:
                        downward_item.setBackground(QBrush(QColor(198, 239, 206)))  # Light green
                    else:
                        downward_item.setBackground(QBrush(QColor(255, 199, 206)))  # Light red
                except ValueError:
                    pass  # Skip coloring if conversion fails

            row += 1

    def get_current_pct_of_company(self, symbol):
        """Get the current percentage of company for a symbol from portfolio data"""
        if symbol in self.portfolio:
            # Check if total_pct_of_company exists in the position data
            total_pct = self.portfolio[symbol].get('total_pct_of_company', None)

            # If we have the value and it's stored as decimal (e.g., 0.085 for 8.5%)
            # then return it directly - already in the right format
            if total_pct is not None:
                return total_pct

            # If we need to calculate it from other data
            if 'os_shares' in self.portfolio[symbol] and self.portfolio[symbol]['os_shares'] > 0:
                # Calculate total shares across all funds
                total_shares = 0
                for fund_name, fund_position in self.portfolio[symbol]['funds'].items():
                    total_shares += fund_position['quantity']

                # Calculate % of company
                os_shares = self.portfolio[symbol]['os_shares']
                return total_shares / os_shares if os_shares > 0 else None

        return None

    def sort_filings_table(self, column_index):
        """Sort the filings table when a header is clicked"""
        # Get column header to determine sort type
        header = self.filings_table.horizontalHeaderItem(column_index).text()

        # If already sorting by this column, reverse the order
        if getattr(self, 'filings_sort_column', None) == column_index:
            filings_sort_reverse = not getattr(self, 'filings_sort_reverse', False)
        else:
            # New sort column
            filings_sort_reverse = False

        # Store the sort state
        self.filings_sort_column = column_index
        self.filings_sort_reverse = filings_sort_reverse

        # Get all data from the table
        table_data = []
        for row in range(self.filings_table.rowCount()):
            row_data = []
            for col in range(self.filings_table.columnCount()):
                item = self.filings_table.item(row, col)
                row_data.append(item.text() if item else "")
            table_data.append(row_data)

        # Define sort key function
        def get_sort_key(row_data):
            value = row_data[column_index]

            # Handle empty values
            if not value:
                if "Filing" in header or "%" in header:
                    return -999999  # Put empty numeric values at the bottom
                return ""

            # Handle percentage columns
            if "%" in header:
                # Remove the % sign and convert to float
                try:
                    return float(value.replace("%", ""))
                except ValueError:
                    return -999999

            # Handle date column
            if header == "Date":
                try:
                    return datetime.strptime(value, "%Y-%m-%d")
                except ValueError:
                    return datetime.min

            # Default - use text value
            return value

        # Sort the data
        table_data.sort(key=get_sort_key, reverse=filings_sort_reverse)

        # Update the table with sorted data
        self.filings_table.setSortingEnabled(False)  # Disable to avoid recursion

        for row, row_data in enumerate(table_data):
            for col, cell_data in enumerate(row_data):
                self.filings_table.item(row, col).setText(cell_data)

        self.filings_table.setSortingEnabled(True)  # Re-enable sorting

    def toggle_filings_frame(self):
        """Toggle the visibility of the filings frame"""
        # Find the Show Filings button in the portfolio frame
        show_filings_btn = None
        for i in range(self.portfolio_group.layout().count()):
            item = self.portfolio_group.layout().itemAt(i)
            if item.layout():  # Check if it's a layout
                for j in range(item.layout().count()):
                    widget = item.layout().itemAt(j).widget()
                    if isinstance(widget, QPushButton) and widget.text() == "Show Filings":
                        show_filings_btn = widget
                        break
                if show_filings_btn:
                    break

        if self.filings_visible:
            # Hide filings frame
            self.middle_panel.setVisible(False)
            self.filings_visible = False

            # Show the "Show Filings" button again
            if show_filings_btn:
                show_filings_btn.setVisible(True)

            # Resize splitter to give space to portfolio and trades only
            self.main_splitter.setSizes([1050, 0, 350])
        else:
            # Show filings frame
            self.middle_panel.setVisible(True)
            self.filings_visible = True

            # Hide the "Show Filings" button since filings are now visible
            if show_filings_btn:
                show_filings_btn.setVisible(False)

            # Make sure filings display is updated
            self.refresh_filings_display()

            # Resize splitter to give equal space to all panels
            self.main_splitter.setSizes([700, 350, 350])

    def import_trades(self):
        """Import trades from Excel file with multiple fund sections"""
        # Ask for file
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Open Orders Excel File", "", "Excel files (*.xls *.xlsx);;All files (*.*)"
        )

        if not file_path:
            return  # User cancelled

        # Check if we have the required dependencies
        try:
            # Try to import xlrd and openpyxl (for different Excel formats)
            dependencies_message = ""

            try:
                import xlrd
            except ImportError:
                dependencies_message += "xlrd (for .xls files) "

            try:
                import openpyxl
            except ImportError:
                if dependencies_message:
                    dependencies_message += "and "
                dependencies_message += "openpyxl (for .xlsx files) "

            if dependencies_message:
                reply = QMessageBox.question(
                    self, "Missing Dependencies",
                    f"The {dependencies_message}packages are required to read Excel files.\n\n"
                    f"Would you like to proceed anyway? (The import might fail)",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )

                if reply != QMessageBox.Yes:
                    return
        except Exception as e:
            # Continue even if we can't check dependencies
            pass

        # Create progress dialog
        progress = QProgressDialog("Importing trades data...", "Cancel", 0, 100, self)
        progress.setWindowTitle("Importing Trades")
        progress.setWindowModality(Qt.WindowModal)
        progress.setValue(0)
        progress.show()

        # Function to run import in background
        class TradesImportWorker(QThread):
            progress_updated = pyqtSignal(int, str)
            import_completed = pyqtSignal(list)
            import_error = pyqtSignal(str)

            def __init__(self, file_path):
                super().__init__()
                self.file_path = file_path

            def run(self):
                try:
                    # Clear data
                    trades = []

                    # Update progress
                    self.progress_updated.emit(10, "Reading Excel file...")

                    try:
                        # Try to read Excel file with pandas
                        import pandas as pd
                        df = pd.read_excel(self.file_path, header=None)

                    except ImportError as e:
                        # Handle missing pandas
                        self.import_error.emit(
                            f"Error: pandas module not found. Please install pandas to use this feature.")
                        return

                    except Exception as e:
                        # If pandas fails, try using alternative methods
                        if "xlrd" in str(e) or "No module named" in str(e):
                            self.progress_updated.emit(15, "Missing Excel library, trying alternative method...")

                            # Try using openpyxl instead
                            try:
                                if self.file_path.lower().endswith('.xlsx'):
                                    import openpyxl
                                    workbook = openpyxl.load_workbook(self.file_path)
                                    sheet = workbook.active

                                    # Convert to DataFrame
                                    data = []
                                    for row in sheet.rows:
                                        data.append([cell.value for cell in row])
                                    df = pd.DataFrame(data)
                                else:
                                    # For .xls files, we need xlrd - inform user
                                    self.import_error.emit(
                                        "Error: Cannot read .xls file without xlrd library.\n\n"
                                        "Please install xlrd using pip:\n"
                                        "pip install xlrd"
                                    )
                                    return
                            except ImportError:
                                self.import_error.emit(
                                    "Error: Required Excel libraries not found.\n\n"
                                    "Please install Excel libraries using pip:\n"
                                    "pip install xlrd openpyxl"
                                )
                                return
                            except Exception as alt_e:
                                self.import_error.emit(f"Error reading Excel file: {str(alt_e)}")
                                return
                        else:
                            # Other error reading Excel file
                            self.import_error.emit(f"Error reading Excel file: {str(e)}")
                            return

                    # Update progress
                    self.progress_updated.emit(30, "Analyzing data...")

                    # Rest of the import process remains the same...
                    # [Original code from import_trades method continues here]

                    # Process sections in the file
                    current_fund = None
                    processing_data = False
                    column_indices = None

                    # Get total number of rows
                    total_rows = len(df)

                    # Iterate through rows to find sections and extract data
                    for i, row in df.iterrows():
                        # Skip empty rows
                        if row.isna().all():
                            continue

                        # Check if row is a section header
                        first_cell = row[0]
                        if isinstance(first_cell, str) and "Fund Open Orders" in first_cell:
                            # Extract fund name (everything before "Fund Open Orders")
                            fund_match = re.match(r'^(.*?)\s+Fund\s+Open\s+Orders', first_cell)
                            if fund_match:
                                current_fund = fund_match.group(1).strip()
                                processing_data = False

                                # Skip Aggregate Fund section
                                if current_fund == "Aggregate":
                                    current_fund = None

                            self.progress_updated.emit(30 + int(20 * i / total_rows), f"Found section: {current_fund}")
                            continue

                        # Check if this is a column header row
                        if current_fund and not processing_data and isinstance(row[0], str) and row[0] == "Side":
                            # Find column indices
                            column_indices = {
                                'side': None,
                                'ticker': None,
                                'limit_px': None,
                                'shares': None
                            }

                            # Find indices for each required column
                            for j, cell in enumerate(row):
                                if cell == "Side":
                                    column_indices['side'] = j
                                elif cell == "Ticker":
                                    column_indices['ticker'] = j
                                elif cell == "Limit PX":
                                    column_indices['limit_px'] = j
                                elif cell == "Shares to Trade":
                                    column_indices['shares'] = j

                            if all(val is not None for val in column_indices.values()):
                                processing_data = True
                                self.progress_updated.emit(30 + int(20 * i / total_rows),
                                                           f"Processing {current_fund} trades...")
                            continue

                        # Process data rows
                        if processing_data and current_fund and column_indices:
                            # Safely get values from the row
                            side_value = row[column_indices['side']]

                            # Skip if side is empty or not a string
                            if not isinstance(side_value, str):
                                continue

                            side = side_value.strip()

                            # Skip "Hold" orders
                            if side == "Hold":
                                continue

                            # Safely get ticker - note that we preserve the original ticker format here
                            # The normalization will happen in on_trades_import_completed
                            ticker_value = row[column_indices['ticker']]
                            ticker = str(ticker_value).strip() if ticker_value is not None and not pd.isna(
                                ticker_value) else ""

                            # Debug ticker format
                            if ticker and " JP" in ticker:
                                self.progress_updated.emit(50 + int(30 * i / total_rows),
                                                           f"Found ticker with JP suffix: {ticker}")

                            # Skip rows with empty ticker
                            if not ticker:
                                continue

                            # Safely get limit price and shares
                            limit_px = row[column_indices['limit_px']] if column_indices['limit_px'] < len(
                                row) and not pd.isna(row[column_indices['limit_px']]) else 0
                            shares = row[column_indices['shares']] if column_indices['shares'] < len(
                                row) and not pd.isna(row[column_indices['shares']]) else 0

                            # Skip rows with zero shares
                            if shares == 0:
                                continue

                            # Add to trades list with original ticker format
                            trades.append({
                                'fund': current_fund,
                                'side': side,
                                'ticker': ticker,  # Keep original format for now
                                'limit_px': limit_px,
                                'shares': shares
                            })

                            self.progress_updated.emit(50 + int(40 * i / total_rows),
                                                       f"Processing {ticker} for {current_fund}...")

                    # Complete
                    self.progress_updated.emit(100, "Import complete")
                    self.import_completed.emit(trades)

                except Exception as e:
                    self.import_error.emit(f"Error importing trades: {str(e)}")
                    import traceback
                    traceback.print_exc()

        # Create and start the worker
        self.trades_import_worker = TradesImportWorker(file_path)
        self.trades_import_worker.progress_updated.connect(
            lambda value, status: self.update_import_progress(progress, value, status)
        )
        self.trades_import_worker.import_completed.connect(self.on_trades_import_completed)
        self.trades_import_worker.import_error.connect(
            lambda msg: self.on_import_error(progress, msg)
        )
        self.trades_import_worker.start()

    def on_trades_import_completed(self, trades):
        """Handle completed trades import and convert to proposed trades"""

        # Temporarily disable auto sorting during the import process
        original_auto_sort = getattr(self, 'auto_sort_enabled', True)
        self.auto_sort_enabled = False

        if not trades:
            QMessageBox.information(self, "Import Complete", "No valid trades were found in the file.")
            return

        # Check if we have a portfolio loaded
        if not self.portfolio:
            QMessageBox.warning(self, "Warning", "Please import a portfolio first before importing trades.")
            return

        # Count of trades that will be processed
        successful_count = 0
        skipped_count = 0

        # Track symbols that were successfully processed
        processed_symbols = set()

        # Create progress dialog for conversion
        progress = QProgressDialog("Converting trades to proposed executions...", "Cancel", 0, len(trades), self)
        progress.setWindowTitle("Processing Trades")
        progress.setWindowModality(Qt.WindowModal)
        progress.setValue(0)
        progress.show()

        # Process each trade
        for i, trade in enumerate(trades):
            # Update progress
            progress.setValue(i)

            try:
                fund_name = trade.get('fund', '')
                raw_ticker = trade.get('ticker', '')

                # Normalize the symbol - now strips off "JP" suffix
                symbol = self.normalize_symbol(raw_ticker)

                # Debug info
                print(f"Original ticker: {raw_ticker}, Normalized: {symbol}")

                side = str(trade.get('side', '')).strip()

                # Validate required fields
                if not fund_name or not symbol or not side:
                    print(f"Missing required field: fund={fund_name}, symbol={symbol}, side={side}")
                    skipped_count += 1
                    continue

                # Get and validate shares value
                try:
                    shares = float(trade.get('shares', 0))
                    if shares == 0:
                        raise ValueError("Shares cannot be zero")
                except (ValueError, TypeError) as e:
                    print(f"Invalid shares value for {symbol}: {trade.get('shares', 0)}, error: {str(e)}")
                    skipped_count += 1
                    continue

                # Get limit price (default to 0 if not present or invalid)
                try:
                    limit_px = float(trade.get('limit_px', 0))
                except (ValueError, TypeError):
                    limit_px = 0

                progress.setLabelText(f"Processing {symbol} for {fund_name}...")

                # List of symbols to try matching in portfolio
                symbols_to_try = [symbol]

                # Also try with JP suffix if portfolio has that format
                jp_symbol = f"{symbol} JP"
                if jp_symbol != raw_ticker:  # Avoid duplicate if raw_ticker already had JP
                    symbols_to_try.append(jp_symbol)

                # Find matching symbol in portfolio
                matched_symbol = None
                for sym_to_try in symbols_to_try:
                    if sym_to_try in self.portfolio:
                        matched_symbol = sym_to_try
                        break

                if not matched_symbol:
                    print(f"Symbol {symbol} not found in portfolio. Tried: {symbols_to_try}")
                    skipped_count += 1
                    continue

                # Use the matched symbol for further processing
                symbol = matched_symbol

                # Check if this fund exists
                if fund_name not in self.fund_names:
                    print(f"Fund {fund_name} not found in portfolio")
                    skipped_count += 1
                    continue

                # Check if fund has this position
                if 'funds' not in self.portfolio[symbol] or fund_name not in self.portfolio[symbol]['funds']:
                    print(f"Fund {fund_name} does not have position for {symbol}")
                    skipped_count += 1
                    continue

                # Get position information
                position = self.portfolio[symbol]
                price = position['price'] if limit_px == 0 else limit_px  # Use limit price if provided

                # Check for valid price
                if price <= 0:
                    print(f"Invalid price for {symbol}: {price}")
                    skipped_count += 1
                    continue

                # Get current quantity
                current_quantity = self.portfolio[symbol]['funds'][fund_name]['quantity']

                # Convert shares to target RAW using similar logic to create_trade_dialog
                target_raw = self.calculate_target_raw_from_shares(
                    fund_name=fund_name,
                    symbol=symbol,
                    current_quantity=current_quantity,
                    trade_shares=shares,
                    side=side
                )

                if target_raw is None:
                    print(f"Failed to calculate target RAW for {symbol} in {fund_name}")
                    skipped_count += 1
                    continue

                # Calculate trade values
                trade_quantity = abs(shares)
                if side.startswith("Sell"):
                    trade_quantity = -trade_quantity

                # Calculate USD value
                trade_value_jpy = abs(shares * price)
                trade_value_usd = trade_value_jpy / self.usd_jpy_rate if self.usd_jpy_rate > 0 else 0

                # Calculate trading days if ADV exists
                trading_days = 0
                if 'adv_10pct' in position and position['adv_10pct'] > 0:
                    trading_days = round(trade_value_usd / position['adv_10pct'] * 10) / 10

                # Create fund-symbol key
                fund_symbol_key = f"{fund_name}:{symbol}"

                # Store signed value for trade direction
                signed_value = -trade_value_usd if side.startswith("Buy") else trade_value_usd

                # Add to proposed executions
                self.proposed_executions[fund_symbol_key] = {
                    'fund': fund_name,
                    'symbol': symbol,
                    'trade_type': 'Buy' if side.startswith("Buy") else 'Sell',
                    'trade_quantity': trade_quantity,
                    'target_raw': target_raw,
                    'trade_value_usd': trade_value_usd,
                    'trade_value_signed': signed_value,
                    'trading_days': trading_days,
                    'target_price': limit_px if limit_px > 0 else None,
                    'pct_to_curr': None  # Will be calculated if target_price is set
                }

                # Calculate % to current price if target price is set
                if limit_px > 0:
                    try:
                        pct_to_curr = (limit_px / position['price'] - 1) * 100

                        # Adjust sign based on trade type
                        if side.startswith("Buy"):
                            # For buys, we want the percentage to be negative (buying below current)
                            pct_to_curr = -abs(pct_to_curr)
                        else:  # Sell
                            # For sells, we want the percentage to be positive (selling above current)
                            pct_to_curr = abs(pct_to_curr)

                        self.proposed_executions[fund_symbol_key]['pct_to_curr'] = pct_to_curr
                    except Exception as e:
                        print(f"Error calculating percent to current: {str(e)}")

                successful_count += 1
                processed_symbols.add(symbol)

            except Exception as e:
                print(f"Error processing trade: {str(e)}")
                import traceback
                traceback.print_exc()
                skipped_count += 1

            # Check if application is processing events
            QApplication.processEvents()
            if progress.wasCanceled():
                break

        # Close progress dialog
        progress.close()

        if successful_count == 0:
            QMessageBox.warning(
                self, "Import Warning",
                f"No trades were successfully imported. {skipped_count} trades were skipped due to errors."
            )
            return

        # Update portfolio display with new trades
        self.refresh_portfolio_display()

        # Update proposed trades table and total USD display
        self.update_proposed_trades_table()
        self.update_total_usd_display()

        # Update the Cash Path charts if they're currently visible
        if self.chart_visible:
            self.create_cash_path_chart()

        # Restore auto sort setting
        self.auto_sort_enabled = original_auto_sort

        # Always sort by the first fund's "Curr." column (relative weight) - smallest to largest
        if len(self.fund_names) > 0:
            # Calculate the column index for the first fund's "Curr." column
            # Fixed columns are: Empty (row num), Symbol, Name, Price (JPY), % of Company
            fixed_columns = 5

            # The Curr. column is the first column for each fund
            rel_weight_col = fixed_columns  # Column index for first fund's Curr. column

            # Set this as the sort column and sort in ascending order (smallest first)
            self.sort_column = rel_weight_col
            self.sort_reverse = False  # False = ascending order so smallest is first

            # Trigger the sorting
            self.sort_portfolio_table(rel_weight_col)

        # Show a success message
        QMessageBox.information(
            self, "Import Successful",
            f"Successfully imported {successful_count} trades affecting {len(processed_symbols)} symbols.\n"
            f"Skipped {skipped_count} trades due to missing positions or funds."
        )

    def normalize_symbol(self, ticker):
        """Normalize symbol to match portfolio format (handle potential differences)"""
        # Handle None or NaN values
        if ticker is None or pd.isna(ticker):
            return ""

        # Convert to string and remove any whitespace
        ticker = str(ticker).strip()

        # If ticker is empty, return empty string
        if not ticker:
            return ""

        # If ticker contains "JP", strip it off - don't keep the JP suffix from the import file
        if " JP" in ticker:
            # Extract just the numeric part
            base_ticker = ticker.split(" JP")[0].strip()
            return base_ticker

        # Check if it's a digit string (possibly with T suffix for Tokyo)
        if ticker.isdigit() or (len(ticker) > 1 and ticker[:-1].isdigit() and ticker[-1].upper() == 'T'):
            # Remove trailing T if present (sometimes used for Tokyo exchange)
            base_ticker = ticker[:-1] if ticker[-1].upper() == 'T' else ticker
            return base_ticker

        # Otherwise return as is
        return ticker

    def calculate_target_raw_from_shares(self, fund_name, symbol, current_quantity, trade_shares, side):
        """
        Calculate the target RAW value based on trade shares
        This reverses the logic used in create_trade_dialog
        """
        try:
            # Make sure we have valid inputs
            if not symbol or symbol not in self.portfolio:
                print(f"Symbol {symbol} not found in portfolio")
                return None

            if not fund_name or fund_name not in self.fund_names:
                print(f"Fund {fund_name} not found")
                return None

            # Validate trade shares
            try:
                trade_shares = float(trade_shares)
            except (ValueError, TypeError):
                print(f"Invalid trade shares value: {trade_shares}")
                return None

            if trade_shares == 0:
                print("Trade shares cannot be zero")
                return None

            position = self.portfolio[symbol]

            # Ensure the fund has this position
            if fund_name not in position.get('funds', {}):
                print(f"Fund {fund_name} does not have position for {symbol}")
                return None

            price = position['price']
            if price <= 0:
                print(f"Invalid price for {symbol}: {price}")
                return None

            # Count securities in the portfolio with weight > 0
            securities_count = 0
            total_portfolio_jpy = 0

            for sym, pos in self.portfolio.items():
                # Skip cash positions
                if pos.get('is_cash', False):
                    continue

                if 'funds' in pos and fund_name in pos['funds']:
                    fund_pos = pos['funds'][fund_name]
                    quantity = fund_pos.get('quantity', 0)

                    if quantity > 0:
                        securities_count += 1
                        # Calculate position value in JPY
                        total_portfolio_jpy += pos['price'] * quantity

            if securities_count == 0 or total_portfolio_jpy <= 0:
                print(f"No valid securities found for fund {fund_name}")
                return None

            # Calculate current position value in JPY
            current_position_jpy = price * current_quantity

            # Calculate trade value in JPY based on side (positive for buys, negative for sells)
            trade_value_jpy = price * abs(trade_shares)
            if side.startswith("Sell"):
                trade_value_jpy = -trade_value_jpy

            # Calculate new position value
            new_position_jpy = current_position_jpy + trade_value_jpy

            # Calculate new portfolio value
            new_portfolio_jpy = total_portfolio_jpy + trade_value_jpy

            # Calculate new weight percentage
            new_weight = (new_position_jpy / new_portfolio_jpy * 100) if new_portfolio_jpy > 0 else 0

            # Calculate average weight
            avg_weight = 100.0 / securities_count if securities_count > 0 else 0

            # Calculate target RAW
            target_raw = new_weight / avg_weight if avg_weight > 0 else 0

            # Log success
            print(f"Calculated target RAW for {symbol} in {fund_name}: {target_raw:.2f}x")

            return target_raw

        except Exception as e:
            print(f"Error calculating target RAW for {symbol} in {fund_name}: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def import_filings(self):
        """Import filings data from Excel file"""
        # Ask for file
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Filings Excel File", "", "Excel files (*.xlsx);;All files (*.*)"
        )

        if not file_path:
            return  # User cancelled

        # Create progress dialog
        progress = QProgressDialog("Importing filings data...", "Cancel", 0, 100, self)
        progress.setWindowTitle("Importing Filings")
        progress.setWindowModality(Qt.WindowModal)
        progress.setValue(0)
        progress.show()

        # Function to run import in background
        class FilingsImportWorker(QThread):
            progress_updated = pyqtSignal(int, str)
            import_completed = pyqtSignal(dict)
            import_error = pyqtSignal(str)

            def __init__(self, file_path):
                super().__init__()
                self.file_path = file_path

            def run(self):
                try:
                    # Clear data
                    filings = {}

                    # Update progress
                    self.progress_updated.emit(10, "Reading Excel file...")

                    # Read Excel file
                    df = pd.read_excel(self.file_path)

                    # Update progress
                    self.progress_updated.emit(30, "Analyzing data...")

                    # Verify required columns
                    required_columns = ["Symbol", "Name", "Last Filing", "Date"]
                    for column in required_columns:
                        if column not in df.columns:
                            self.import_error.emit(f"Required column '{column}' not found in the Excel file")
                            return

                    # Get total number of rows
                    total_rows = len(df)

                    # Process each row
                    for i, row in df.iterrows():
                        symbol = str(row["Symbol"]).strip()
                        name = str(row["Name"]).strip()

                        # Handle Date column
                        date = None
                        if "Date" in row and not pd.isna(row["Date"]):
                            if isinstance(row["Date"], datetime):
                                date = row["Date"].strftime("%Y-%m-%d")
                            else:
                                date = str(row["Date"]).strip()

                        # Handle Last Filing column - store as float percentage
                        last_filing = None
                        if "Last Filing" in row and not pd.isna(row["Last Filing"]):
                            filing_value = row["Last Filing"]
                            # If it's a string with % sign, convert accordingly
                            if isinstance(filing_value, str) and "%" in filing_value:
                                filing_value = filing_value.replace("%", "").strip()
                                try:
                                    last_filing = float(filing_value) / 100.0  # Convert to decimal
                                except ValueError:
                                    last_filing = None
                            else:
                                # Try to convert directly to float
                                try:
                                    last_filing = float(filing_value)
                                    # If the value is already in decimal form (e.g., 0.085), use it directly
                                    if last_filing > 1.0:  # If > 1.0, assume it's a percentage value
                                        last_filing /= 100.0
                                except (ValueError, TypeError):
                                    last_filing = None

                        # Update status
                        self.progress_updated.emit(
                            30 + int(65 * i / total_rows),
                            f"Processing {symbol}..."
                        )

                        # Skip empty rows
                        if not symbol or pd.isna(symbol):
                            continue

                        # Add to filings dictionary
                        filings[symbol] = {
                            'name': name,
                            'date': date,
                            'last_filing': last_filing
                        }

                    # Complete
                    self.progress_updated.emit(100, "Import complete")
                    self.import_completed.emit(filings)

                except Exception as e:
                    self.import_error.emit(f"Error importing filings: {str(e)}")
                    import traceback
                    traceback.print_exc()

        # Create and start the worker
        self.filings_import_worker = FilingsImportWorker(file_path)
        self.filings_import_worker.progress_updated.connect(
            lambda value, status: self.update_import_progress(progress, value, status)
        )
        self.filings_import_worker.import_completed.connect(self.on_filings_import_completed)
        self.filings_import_worker.import_error.connect(
            lambda msg: self.on_import_error(progress, msg)
        )
        self.filings_import_worker.start()

    def update_fund_headers(self):
        """Update the fund header table to match the main table columns"""
        if not hasattr(self, 'header_table') or not hasattr(self, 'portfolio_table'):
            return

        fixed_columns = ["", "Symbol", "Name", "Price (JPY)", "% of Company"]  # Added "% of Company" column
        fund_columns = ["Curr.", "New"]

        # Get column count from main table
        col_count = self.portfolio_table.columnCount()
        self.header_table.setColumnCount(col_count)

        # Synchronize column widths
        for col in range(col_count):
            self.header_table.setColumnWidth(col, self.portfolio_table.columnWidth(col))

        # Clear the header table
        self.header_table.clearContents()

        # Set fixed columns to empty
        for col in range(len(fixed_columns)):
            item = QTableWidgetItem("")
            self.header_table.setItem(0, col, item)

        # Set fund names with different colors
        fund_colors = [
            QColor(230, 242, 255),  # Light blue
            QColor(230, 255, 230),  # Light green
            QColor(255, 242, 230),  # Light orange
            QColor(242, 230, 255)  # Light purple
        ]

        # Set row height based on font size
        row_height = self.current_font_size * 2 + 10
        self.header_table.setRowHeight(0, row_height)

        # Create bold font for fund headers
        bold_font = QFont()
        bold_font.setPointSize(self.current_font_size)
        bold_font.setBold(True)

        # Set fund names
        for fund_idx, fund_name in enumerate(self.fund_names):
            # Calculate first column for this fund
            first_col = len(fixed_columns) + fund_idx * len(fund_columns)

            # Create item for fund name
            item = QTableWidgetItem(fund_name)
            item.setTextAlignment(Qt.AlignCenter)

            # Set background color - cycle through colors for each fund
            color_idx = fund_idx % len(fund_colors)
            brush = QBrush(fund_colors[color_idx])
            item.setBackground(brush)

            # Set bold font with current font size
            item.setFont(bold_font)

            # Add to first column of this fund
            self.header_table.setItem(0, first_col, item)

            # Set span to cover all columns for this fund
            self.header_table.setSpan(0, first_col, 1, len(fund_columns))

    def on_portfolio_double_click(self, row, column):
        """Handle double-click on portfolio table to open trade dialog"""
        symbol_item = self.portfolio_table.item(row, 1)  # Symbol column is at index 1
        if symbol_item:
            # First select the row to ensure position details are updated
            self.portfolio_table.selectRow(row)
            # Then open the trade dialog
            self.create_trade_dialog()

    def create_position_frame(self, parent_layout):
        position_group = QGroupBox("Position Details")
        position_layout = QGridLayout(position_group)

        # Row 1: Symbol and Name
        position_layout.addWidget(QLabel("Symbol:"), 0, 0)
        self.symbol_label = QLabel("")
        position_layout.addWidget(self.symbol_label, 0, 1)

        position_layout.addWidget(QLabel("Name:"), 0, 2)
        self.name_label = QLabel("")
        position_layout.addWidget(self.name_label, 0, 3)

        # Row 2: Price and Quantity
        position_layout.addWidget(QLabel("Price (JPY):"), 1, 0)
        self.price_label = QLabel("")
        position_layout.addWidget(self.price_label, 1, 1)

        position_layout.addWidget(QLabel("Quantity:"), 1, 2)
        self.quantity_label = QLabel("")
        position_layout.addWidget(self.quantity_label, 1, 3)

        # Row 3: Values
        position_layout.addWidget(QLabel("Value (JPY):"), 2, 0)
        self.value_jpy_label = QLabel("")
        position_layout.addWidget(self.value_jpy_label, 2, 1)

        position_layout.addWidget(QLabel("Value (USD):"), 2, 2)
        self.value_usd_label = QLabel("")
        position_layout.addWidget(self.value_usd_label, 2, 3)

        # Row 4: Weights
        position_layout.addWidget(QLabel("Weight:"), 3, 0)
        self.weight_label = QLabel("")
        position_layout.addWidget(self.weight_label, 3, 1)

        position_layout.addWidget(QLabel("Current Rel. Weight:"), 3, 2)
        self.rel_weight_label = QLabel("")
        position_layout.addWidget(self.rel_weight_label, 3, 3)

        # Add to parent layout
        parent_layout.addWidget(position_group)

    def create_trade_frame(self, parent_layout):
        trade_group = QGroupBox("Propose Trade")
        trade_layout = QVBoxLayout(trade_group)

        # Upper row - Input fields
        input_layout = QHBoxLayout()

        # Current relative weight display
        input_layout.addWidget(QLabel("Current RAW:"))
        self.current_raw_label = QLabel("")
        input_layout.addWidget(self.current_raw_label)

        # New relative weight input
        input_layout.addWidget(QLabel("New RAW:"))
        self.new_raw_input = QLineEdit()
        input_layout.addWidget(self.new_raw_input)

        # Trade calculation button
        self.calculate_btn = QPushButton("Calculate Trade")
        self.calculate_btn.clicked.connect(self.calculate_trade)
        self.calculate_btn.setEnabled(False)  # Disabled initially
        input_layout.addWidget(self.calculate_btn)

        trade_layout.addLayout(input_layout)

        # Lower row - Calculated results
        results_layout = QHBoxLayout()

        results_layout.addWidget(QLabel("Trade Type:"))
        self.trade_type_label = QLabel("")
        results_layout.addWidget(self.trade_type_label)

        results_layout.addWidget(QLabel("Traded Shares:"))
        self.traded_shares_label = QLabel("")
        results_layout.addWidget(self.traded_shares_label)

        results_layout.addWidget(QLabel("Traded JPY:"))
        self.traded_jpy_label = QLabel("")
        results_layout.addWidget(self.traded_jpy_label)

        results_layout.addWidget(QLabel("Traded USD:"))
        self.traded_usd_label = QLabel("")
        results_layout.addWidget(self.traded_usd_label)

        results_layout.addWidget(QLabel("Trading Days:"))
        self.trading_days_label = QLabel("")
        results_layout.addWidget(self.trading_days_label)

        trade_layout.addLayout(results_layout)

        # Add to proposed trades button
        button_layout = QHBoxLayout()

        self.add_trade_btn = QPushButton("Add to Proposed Trades")
        self.add_trade_btn.clicked.connect(self.add_to_proposed_trades)
        self.add_trade_btn.setEnabled(False)  # Disabled initially
        button_layout.addWidget(self.add_trade_btn)

        trade_layout.addLayout(button_layout)

        # Add to parent layout
        parent_layout.addWidget(trade_group)

    def create_proposed_trades_frame(self, parent_layout):
        # Create a vertical splitter to allow resizing between proposed trades and cash path
        self.right_splitter = QSplitter(Qt.Vertical)

        # Create the trades group box
        trades_group = QGroupBox("Proposed Trades")
        trades_layout = QVBoxLayout(trades_group)

        # Top button bar and total display
        top_layout = QHBoxLayout()

        # Total USD display
        self.total_usd_label = QLabel("Net Total: $0.00")
        top_layout.addWidget(self.total_usd_label)

        # Add spacer
        top_layout.addStretch()

        # Cash path button
        self.cash_path_btn = QPushButton("Show Cash Path")
        self.cash_path_btn.clicked.connect(self.toggle_cash_path_chart)
        top_layout.addWidget(self.cash_path_btn)

        trades_layout.addLayout(top_layout)

        # Proposed trades table
        self.proposed_trades_table = QTableWidget()
        self.proposed_trades_table.setAlternatingRowColors(True)
        self.proposed_trades_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.proposed_trades_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.proposed_trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.proposed_trades_table.horizontalHeader().setStretchLastSection(False)

        # Set up columns
        columns = ["Trade Type", "Ticker", "Name", "Shares", "USD Value", "Trading Days",
                   "Avg Rel Weight", "Target Price", "% to Curr Price"]
        self.proposed_trades_table.setColumnCount(len(columns))
        self.proposed_trades_table.setHorizontalHeaderLabels(columns)

        # Set column widths
        self.proposed_trades_table.setColumnWidth(0, 80)  # Trade Type
        self.proposed_trades_table.setColumnWidth(1, 80)  # Ticker
        self.proposed_trades_table.setColumnWidth(2, 150)  # Name
        self.proposed_trades_table.setColumnWidth(3, 90)  # Shares
        self.proposed_trades_table.setColumnWidth(4, 90)  # USD Value
        self.proposed_trades_table.setColumnWidth(5, 90)  # Trading Days
        self.proposed_trades_table.setColumnWidth(6, 90)  # Avg Rel Weight
        self.proposed_trades_table.setColumnWidth(7, 100)  # Target Price
        self.proposed_trades_table.setColumnWidth(8, 100)  # % to Curr Price

        # Connect double-click event
        self.proposed_trades_table.cellDoubleClicked.connect(self.on_proposed_trade_double_click)

        # Connect selection changed event
        self.proposed_trades_table.itemSelectionChanged.connect(self.on_proposed_trade_select)

        trades_layout.addWidget(self.proposed_trades_table)

        # Bottom buttons
        button_layout = QHBoxLayout()

        # Edit button
        self.edit_trade_btn = QPushButton("Edit Selected Trade")
        self.edit_trade_btn.clicked.connect(self.edit_proposed_trade)
        self.edit_trade_btn.setEnabled(False)  # Disabled initially
        button_layout.addWidget(self.edit_trade_btn)

        # Delete button
        self.delete_trade_btn = QPushButton("Delete Selected Trade")
        self.delete_trade_btn.clicked.connect(self.delete_proposed_trade)
        self.delete_trade_btn.setEnabled(False)  # Disabled initially
        button_layout.addWidget(self.delete_trade_btn)

        # Clear all button
        clear_btn = QPushButton("Clear All Trades")
        clear_btn.clicked.connect(self.clear_proposed_executions)
        button_layout.addWidget(clear_btn)

        # Export button
        export_btn = QPushButton("Export Trades")
        export_btn.clicked.connect(self.export_proposed_trades)
        button_layout.addWidget(export_btn)

        trades_layout.addLayout(button_layout)

        # Add the trades group to the top part of the splitter
        self.right_splitter.addWidget(trades_group)

        # Create chart frame (initially hidden but will be in the bottom part of the splitter)
        self.chart_frame = QWidget()
        self.chart_layout = QVBoxLayout(self.chart_frame)
        self.chart_frame.setVisible(False)
        self.right_splitter.addWidget(self.chart_frame)

        # Set initial sizes with more space for the trades table
        self.right_splitter.setSizes([350, 0])  # All space to trades initially since chart is hidden

        # Add the splitter to the parent layout
        parent_layout.addWidget(self.right_splitter)

    def update_exchange_rate(self):
        """
        Update the USD/JPY exchange rate - modified to check for JPY price
        in the portfolio first instead of always using YFinance
        """
        # First check if JPY exists in portfolio and use its price as the exchange rate
        if 'JPY' in self.portfolio and self.portfolio['JPY']['is_cash']:
            # For JPY position, the price field stores the USD/JPY rate
            jpy_position = self.portfolio['JPY']
            if jpy_position['price'] > 1.0:  # Make sure it's a reasonable rate, not just 1.0
                self.usd_jpy_rate = jpy_position['price']
                self.exchange_rate_label.setText(f"USD/JPY: {self.usd_jpy_rate:.2f}")

                # Update any USD-dependent values in the portfolio
                self.refresh_portfolio_display()
                return

        # If JPY not found or rate not available, fall back to YFinance
        class ExchangeRateWorker(QThread):
            rate_updated = pyqtSignal(float)

            def run(self):
                try:
                    ticker = yf.Ticker("USDJPY=X")
                    info = ticker.info
                    if 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
                        rate = info['regularMarketPrice']
                        self.rate_updated.emit(rate)
                except Exception as e:
                    print(f"Error fetching exchange rate: {str(e)}")

        # Create and start the worker
        self.exchange_worker = ExchangeRateWorker()
        self.exchange_worker.rate_updated.connect(self.on_exchange_rate_updated)
        self.exchange_worker.start()

    def on_exchange_rate_updated(self, rate):
        """Handle exchange rate update"""
        self.usd_jpy_rate = rate
        self.exchange_rate_label.setText(f"USD/JPY: {rate:.2f}")

        # Update USD cash position price if it exists
        if 'USD' in self.portfolio and self.portfolio['USD']['is_cash']:
            self.portfolio['USD']['price'] = rate

            # If using YFinance pricing, also update the display
            if self.use_yfinance_pricing:
                self.refresh_portfolio_display()

    def import_portfolio(self):
        """
        Import portfolio from Excel file - modified to extract USD/JPY rate
        from the portfolio data
        """
        # Ask for file
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel File", "", "Excel files (*.xlsx);;All files (*.*)"
        )

        if not file_path:
            return  # User cancelled

        # Create progress dialog
        progress = QProgressDialog("Importing portfolio data...", "Cancel", 0, 100, self)
        progress.setWindowTitle("Importing Portfolio")
        progress.setWindowModality(Qt.WindowModal)
        progress.setValue(0)
        progress.show()

        # Function to run import in background
        class ImportWorker(QThread):
            progress_updated = pyqtSignal(int, str)
            import_completed = pyqtSignal(dict, list, float)
            import_error = pyqtSignal(str)

            def __init__(self, file_path, use_yfinance):
                super().__init__()
                self.file_path = file_path
                self.use_yfinance = use_yfinance

            def run(self):
                try:
                    # Clear data
                    portfolio = {}
                    fund_names = []

                    # Default exchange rate (will be updated if JPY is in portfolio)
                    usd_jpy_rate = 0.0

                    # Update progress
                    self.progress_updated.emit(10, "Reading Excel file...")

                    # Read Excel file
                    df = pd.read_excel(self.file_path)

                    # Update progress
                    self.progress_updated.emit(30, "Analyzing data...")

                    # Verify required columns
                    required_columns = ["Symbol", "Name", "Quantity"]
                    for column in required_columns:
                        if column not in df.columns:
                            self.import_error.emit(f"Required column '{column}' not found in the Excel file")
                            return

                    # Check for Fund column
                    has_fund_column = "Fund" in df.columns

                    # Check for 10% 3m ADV column
                    has_adv_column = "10% 3m ADV" in df.columns

                    # Check for Price column
                    has_price_column = "Price" in df.columns

                    # Check for OS (Outstanding Shares) column
                    has_os_column = "OS" in df.columns

                    # Check for % of Company column
                    has_pct_of_company_column = "% of Company" in df.columns

                    if not has_price_column and not self.use_yfinance:
                        self.import_error.emit("Price column not found in Excel file and YFinance pricing is disabled")
                        return

                    # Get total number of rows
                    total_rows = len(df)

                    # Get unique funds if Fund column exists
                    if has_fund_column:
                        # Use unique funds from the file
                        fund_names = df["Fund"].dropna().unique().tolist()
                    else:
                        # Use default fund
                        fund_names = ["Default"]

                    # Process each row
                    for i, row in df.iterrows():
                        symbol = str(row["Symbol"]).strip()
                        name = str(row["Name"]).strip()
                        quantity = float(row["Quantity"])

                        # Get fund if available
                        if has_fund_column:
                            fund = str(row["Fund"]).strip()
                        else:
                            fund = "Default"

                        # Get 10% 3m ADV if available
                        adv_10pct = 0
                        if has_adv_column and not pd.isna(row["10% 3m ADV"]):
                            adv_10pct = float(row["10% 3m ADV"])

                        # Get OS if available
                        os_shares = 0
                        if has_os_column and not pd.isna(row["OS"]):
                            os_shares = float(row["OS"])

                        # Get % of Company if available
                        pct_of_company = 0
                        if has_pct_of_company_column and not pd.isna(row["% of Company"]):
                            pct_of_company = float(row["% of Company"])
                        elif os_shares > 0 and quantity > 0:
                            # Calculate % of company if not provided but we have OS and quantity
                            pct_of_company = quantity / os_shares if os_shares > 0 else 0

                        # Update status
                        self.progress_updated.emit(
                            30 + int(65 * i / total_rows),
                            f"Processing {symbol} for fund {fund}..."
                        )

                        # Skip empty rows
                        if not symbol or pd.isna(symbol):
                            continue

                        is_cash = symbol.upper() in ["JPY", "USD"]
                        currency = symbol.upper() if is_cash else "JPY"

                        # Get price - either from Excel or YFinance
                        if has_price_column and not pd.isna(row["Price"]):
                            # Use price from Excel
                            price = float(row["Price"])

                            # If this is the JPY cash position, store its price as the exchange rate
                            if symbol.upper() == "JPY" and is_cash and price > 1.0:
                                usd_jpy_rate = price
                        elif is_cash:
                            if symbol.upper() == "JPY":
                                # For JPY cash position, price should be the USD/JPY rate from Excel,
                                # but if it wasn't provided, set default to 1.0
                                price = 1.0
                            else:  # USD
                                # For USD cash position, keep price at 1.0 (or set to the inverse of JPY rate if available)
                                price = 1.0
                        elif self.use_yfinance:
                            # Use YFinance for non-cash positions if enabled
                            try:
                                # Automatically append .T for Japanese stocks
                                fetch_symbol = f"{symbol}.T" if symbol not in ["JPY", "USD"] else symbol
                                ticker = yf.Ticker(fetch_symbol)
                                info = ticker.info
                                if 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
                                    price = info['regularMarketPrice']
                                else:
                                    # Default price if not available
                                    price = 0.0
                            except Exception as e:
                                # Default price if error
                                price = 0.0
                        else:
                            # No price available
                            price = 0.0

                        # Initialize symbol data if not exists in portfolio
                        if symbol not in portfolio:
                            portfolio[symbol] = {
                                'name': name,
                                'price': price,
                                'is_cash': is_cash,
                                'adv_10pct': adv_10pct,
                                'currency': currency,
                                'os_shares': os_shares,  # Store outstanding shares
                                'funds': {}  # Store fund-specific data
                            }

                        # Add fund-specific data
                        portfolio[symbol]['funds'][fund] = {
                            'quantity': quantity,
                            'pct_of_company': pct_of_company  # Store % of company for this fund
                        }

                    # Complete
                    self.progress_updated.emit(100, "Import complete")
                    self.import_completed.emit(portfolio, fund_names, usd_jpy_rate)

                except Exception as e:
                    self.import_error.emit(f"Error importing portfolio: {str(e)}")

        # Create and start the worker
        self.import_worker = ImportWorker(file_path, self.use_yfinance_pricing)
        self.import_worker.progress_updated.connect(
            lambda value, status: self.update_import_progress(progress, value, status)
        )
        self.import_worker.import_completed.connect(self.on_import_completed)
        self.import_worker.import_error.connect(
            lambda msg: self.on_import_error(progress, msg)
        )
        self.import_worker.start()

    def update_import_progress(self, progress_dialog, value, status):
        """Update import progress dialog"""
        progress_dialog.setValue(value)
        progress_dialog.setLabelText(status)

    def on_import_error(self, progress_dialog, message):
        """Handle import error"""
        progress_dialog.close()
        QMessageBox.critical(self, "Import Error", message)

    def on_import_completed(self, portfolio, fund_names, usd_jpy_rate):
        """
        Handle completed import - ensuring the USD/JPY rate is properly stored and displayed,
        and automatically sorting the portfolio table
        """
        # Store the data
        self.portfolio = portfolio
        self.fund_names = fund_names

        # Get USD/JPY rate from portfolio - use the JPY cash position's price as the exchange rate
        if 'JPY' in portfolio and portfolio['JPY']['is_cash'] and portfolio['JPY']['price'] > 1.0:
            self.usd_jpy_rate = portfolio['JPY']['price']
            self.exchange_rate_label.setText(f"USD/JPY: {self.usd_jpy_rate:.2f}")

            # Also update USD price if it exists
            if 'USD' in portfolio:
                # USD price should match the JPY cash position's price
                portfolio['USD']['price'] = self.usd_jpy_rate
        # Only use YFinance rate as fallback
        elif usd_jpy_rate > 0:
            self.usd_jpy_rate = usd_jpy_rate
            self.exchange_rate_label.setText(f"USD/JPY: {usd_jpy_rate:.2f}")

        # Ensure we always have a valid USD/JPY rate
        if self.usd_jpy_rate <= 1.0:
            # Use a default rate of 100 as a fallback if no valid rate is available
            self.usd_jpy_rate = 100.0
            self.exchange_rate_label.setText(f"USD/JPY: {self.usd_jpy_rate:.2f} (default)")

        # Update portfolio display
        self.refresh_portfolio_display()

        # After refreshing the display, automatically sort the portfolio table
        # by the first fund's "Curr." column (relative weight)
        if len(self.fund_names) > 0:
            # Calculate the column index for the first fund's "Curr." column
            # Fixed columns are: Empty (row num), Symbol, Name, Price (JPY), % of Company
            fixed_columns = 5  # Updated from 4 to 5 with new column

            # Each fund has two columns (Curr. and New)
            # The Curr. column is the first column for each fund
            rel_weight_col = fixed_columns  # Column index for first fund's Curr. column

            # Set this as the sort column and sort in descending order (largest first)
            self.sort_column = rel_weight_col
            self.sort_reverse = False  # Descending order so largest is first

            # Trigger the sorting
            self.sort_portfolio_table(rel_weight_col)

    def refresh_prices(self):
        """Refresh prices from YFinance"""
        if not self.portfolio:
            return

        # Create progress dialog
        progress = QProgressDialog("Refreshing prices...", "Cancel", 0, len(self.portfolio), self)
        progress.setWindowTitle("Refreshing Prices")
        progress.setWindowModality(Qt.WindowModal)
        progress.setValue(0)
        progress.show()

        class PriceWorker(QThread):
            price_updated = pyqtSignal(str, float)
            progress_updated = pyqtSignal(int)
            completed = pyqtSignal()
            error = pyqtSignal(str)

            def __init__(self, portfolio):
                super().__init__()
                self.portfolio = portfolio

            def run(self):
                try:
                    count = 0

                    # First, update exchange rate
                    try:
                        ticker = yf.Ticker("USDJPY=X")
                        info = ticker.info
                        if 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
                            rate = info['regularMarketPrice']
                            self.price_updated.emit("USD/JPY", rate)
                    except Exception as e:
                        print(f"Error fetching exchange rate: {str(e)}")

                    # Then update all other prices
                    for symbol, position in self.portfolio.items():
                        if symbol == "JPY":
                            # Skip JPY as its price is always 1.0
                            count += 1
                            self.progress_updated.emit(count)
                            continue

                        if not position['is_cash'] or (position['is_cash'] and symbol == 'USD'):
                            try:
                                if not position['is_cash']:
                                    # Automatically append .T for Japanese stocks
                                    fetch_symbol = f"{symbol}.T" if symbol not in ["JPY", "USD"] else symbol

                                    ticker = yf.Ticker(fetch_symbol)
                                    info = ticker.info
                                    if 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
                                        price = info['regularMarketPrice']
                                        self.price_updated.emit(symbol, price)
                            except Exception as e:
                                print(f"Error refreshing price for {symbol}: {str(e)}")

                        count += 1
                        self.progress_updated.emit(count)

                    self.completed.emit()

                except Exception as e:
                    self.error.emit(f"Error refreshing prices: {str(e)}")

        # Create and start worker
        self.price_worker = PriceWorker(self.portfolio)
        self.price_worker.price_updated.connect(self.on_price_updated)
        self.price_worker.progress_updated.connect(progress.setValue)
        self.price_worker.completed.connect(progress.close)
        self.price_worker.error.connect(
            lambda msg: self.on_price_refresh_error(progress, msg)
        )
        self.price_worker.start()

    def on_price_updated(self, symbol, price):
        """Handle price update for a symbol"""
        if symbol == "USD/JPY":
            # Update exchange rate
            self.usd_jpy_rate = price
            self.exchange_rate_label.setText(f"USD/JPY: {price:.2f}")

            # Also update USD cash position price
            if 'USD' in self.portfolio and self.portfolio['USD']['is_cash']:
                self.portfolio['USD']['price'] = price
        else:
            # Update regular symbol price
            if symbol in self.portfolio:
                self.portfolio[symbol]['price'] = price

    def on_price_refresh_error(self, progress_dialog, message):
        """Handle price refresh error"""
        progress_dialog.close()
        QMessageBox.warning(self, "Price Refresh Error", message)

    def refresh_portfolio_display(self):
        """Refresh the portfolio display"""
        # Store currently selected position
        selected_symbol = None
        if self.portfolio_table.selectionModel().hasSelection():
            current_row = self.portfolio_table.currentRow()
            if current_row >= 0:
                symbol_item = self.portfolio_table.item(current_row, 1)  # Symbol is column 1
                if symbol_item:
                    selected_symbol = symbol_item.text()

        # Store existing rel_weight values from the table before refreshing
        existing_rel_weights = {}
        for row in range(self.portfolio_table.rowCount()):
            symbol_item = self.portfolio_table.item(row, 1)  # Symbol is column 1
            if symbol_item:
                symbol = symbol_item.text()
                existing_rel_weights[symbol] = {}

                # Get rel_weight values for each fund
                for fund_idx, fund_name in enumerate(self.fund_names):
                    fixed_columns = 5  # Updated: Empty, Symbol, Name, Price (JPY), % of Company
                    rel_weight_col = fixed_columns + fund_idx * 2  # Each fund has 2 columns (Curr + New)

                    rel_weight_item = self.portfolio_table.item(row, rel_weight_col)
                    if rel_weight_item and rel_weight_item.text():
                        # Remove the 'x' from the end and convert to float
                        rel_weight_text = rel_weight_item.text().replace('x', '')
                        try:
                            rel_weight_value = float(rel_weight_text)
                            existing_rel_weights[symbol][fund_name] = rel_weight_value
                        except ValueError:
                            pass

        # Define which columns to display
        fixed_columns = ["", "Symbol", "Name", "Price (JPY)", "% of Company"]  # Added "% of Company" column
        fund_columns = ["Curr.", "New"]

        total_columns = len(fixed_columns) + len(fund_columns) * len(self.fund_names)

        # Clear and reset table
        self.portfolio_table.setRowCount(0)
        self.portfolio_table.setColumnCount(total_columns)

        # Set up headers
        headers = []

        # Add fixed column headers
        for col in fixed_columns:
            headers.append(col)

        # Add fund-specific column headers
        for fund in self.fund_names:
            for col in fund_columns:
                headers.append(f"{fund} - {col}")

        self.portfolio_table.setHorizontalHeaderLabels(headers)

        # Set up column widths and alignment - adjusted for font size
        font_scaling_factor = self.current_font_size / 9.0  # Scale relative to default font size of 9pt

        # Row number column
        self.portfolio_table.setColumnWidth(0, int(40 * font_scaling_factor))

        # Symbol column
        self.portfolio_table.setColumnWidth(1, int(80 * font_scaling_factor))

        # Name column
        self.portfolio_table.setColumnWidth(2, int(150 * font_scaling_factor))

        # Other fixed columns
        for i in range(3, len(fixed_columns)):
            self.portfolio_table.setColumnWidth(i, int(100 * font_scaling_factor))

        # Fund-specific columns
        for i in range(len(fixed_columns), total_columns):
            # Set all fund columns to right alignment for consistency
            column_header = headers[i]
            if "Value" in column_header or "Weight" in column_header or "Shares" in column_header:
                self.portfolio_table.setColumnWidth(i, int(110 * font_scaling_factor))
            else:
                self.portfolio_table.setColumnWidth(i, int(90 * font_scaling_factor))

        # Calculate values for each position
        all_positions = {}
        fund_totals = {}

        # Check if we have a USD/JPY rate, if not, use the JPY position price as the rate
        if (self.usd_jpy_rate <= 1.0 and 'JPY' in self.portfolio and
                self.portfolio['JPY']['is_cash'] and self.portfolio['JPY']['price'] > 1.0):
            self.usd_jpy_rate = self.portfolio['JPY']['price']
            self.exchange_rate_label.setText(f"USD/JPY: {self.usd_jpy_rate:.2f}")

        # First pass: calculate initial data for each position
        for symbol, position in self.portfolio.items():
            # Skip JPY and USD positions completely
            if symbol in ["JPY", "USD"]:
                continue

            if 'funds' not in position:
                continue

            for fund_name, fund_position in position['funds'].items():
                if fund_name not in self.fund_names:
                    continue

                quantity = fund_position['quantity']
                price = position['price']
                value_jpy = price * quantity

                # Initialize fund total if needed
                if fund_name not in fund_totals:
                    fund_totals[fund_name] = 0

                fund_totals[fund_name] += value_jpy

                # Initialize position data if needed
                if symbol not in all_positions:
                    all_positions[symbol] = {
                        'symbol': symbol,
                        'name': position['name'],
                        'price': position['price'],
                        'is_cash': position['is_cash'],
                        'adv_10pct': position.get('adv_10pct', 0),
                        'funds': {},
                        'total_pct_of_company': 0  # Initialize the total % of company
                    }

                # Store raw data for later calculations
                all_positions[symbol]['funds'][fund_name] = {
                    'quantity': quantity,
                    'value_jpy': value_jpy,
                    'pct_of_company': fund_position.get('pct_of_company', 0)  # Get % of company from fund position
                }

                # Calculate total_pct_of_company as sum across all funds
                all_positions[symbol]['total_pct_of_company'] += fund_position.get('pct_of_company', 0)

        # Calculate fund USD totals for weight calculations
        fund_totals_usd = {}
        for fund_name in self.fund_names:
            fund_totals_usd[fund_name] = 0

        # Calculate USD values for all positions
        for symbol, pos_data in all_positions.items():
            for fund_name in self.fund_names:
                if fund_name not in pos_data['funds']:
                    continue

                fund_position = pos_data['funds'][fund_name]
                # Calculate USD value
                value_usd = fund_position['value_jpy'] / self.usd_jpy_rate if self.usd_jpy_rate > 0 else 0

                fund_position['value_usd'] = value_usd
                fund_totals_usd[fund_name] += value_usd

        # Calculate positions in each fund for relative weight calculation
        positions_in_fund = {}
        for fund_name in self.fund_names:
            positions_in_fund[fund_name] = sum(1 for p in all_positions.values()
                                               if 'funds' in p and fund_name in p['funds'])

        # Second pass: calculate weights and check for proposed trades
        for symbol, pos_data in all_positions.items():
            for fund_name in self.fund_names:
                if fund_name not in pos_data['funds']:
                    continue

                fund_position = pos_data['funds'][fund_name]
                fund_total_usd = fund_totals_usd.get(fund_name, 0)

                # Calculate weight based on USD values
                fund_position['weight'] = (
                        fund_position['value_usd'] / fund_total_usd * 100) if fund_total_usd > 0 else 0

                # Calculate relative weight
                num_positions = positions_in_fund.get(fund_name, 0)
                avg_weight = 100.0 / num_positions if num_positions > 0 else 0

                # If we have an existing rel_weight value from before, use that instead of recalculating
                if symbol in existing_rel_weights and fund_name in existing_rel_weights[symbol]:
                    fund_position['rel_weight'] = existing_rel_weights[symbol][fund_name]
                else:
                    fund_position['rel_weight'] = fund_position['weight'] / avg_weight if avg_weight > 0 else 0

                # Check for proposed executions
                fund_symbol_key = f"{fund_name}:{symbol}"

                if fund_symbol_key in self.proposed_executions:
                    execution = self.proposed_executions[fund_symbol_key]
                    fund_position['new_rel_weight'] = execution['target_raw']
                else:
                    fund_position['new_rel_weight'] = 0

        # Define colors for fund backgrounds
        fund_colors = [
            QColor(230, 242, 255),  # Light blue
            QColor(230, 255, 230),  # Light green
            QColor(255, 242, 230),  # Light orange
            QColor(242, 230, 255)  # Light purple
        ]

        # Define VERY bright colors for trade types - much more vibrant than before
        buy_color = QColor(150, 255, 150)  # Bright green for buys
        sell_color = QColor(255, 150, 150)  # Bright red for sells

        # Set row height based on font size
        row_height = self.current_font_size * 2 + 10

        # We only have regular positions now (cash positions excluded)
        row = 0
        for symbol, pos_data in all_positions.items():
            self.portfolio_table.insertRow(row)

            # Set row height based on font size
            self.portfolio_table.setRowHeight(row, row_height)

            # Check if this position has any trades and determine the trade type
            has_buy = False
            has_sell = False

            # Check for trades across all funds
            for fund_name in self.fund_names:
                fund_symbol_key = f"{fund_name}:{symbol}"
                if fund_symbol_key in self.proposed_executions:
                    execution = self.proposed_executions[fund_symbol_key]
                    if execution['trade_type'] == 'Buy':
                        has_buy = True
                    elif execution['trade_type'] == 'Sell':
                        has_sell = True

            # Row number (first column) - Initialize with placeholder
            row_num_item = QTableWidgetItem("")
            self.portfolio_table.setItem(row, 0, row_num_item)

            # Symbol
            symbol_item = QTableWidgetItem(symbol)
            self.portfolio_table.setItem(row, 1, symbol_item)

            # Name
            name_item = QTableWidgetItem(pos_data['name'])
            self.portfolio_table.setItem(row, 2, name_item)

            # Price
            price_item = QTableWidgetItem(f"{int(pos_data['price']):,}")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.portfolio_table.setItem(row, 3, price_item)

            # % of Company (new column)
            pct_of_company_item = QTableWidgetItem(f"{pos_data['total_pct_of_company'] * 100:.2f}%")
            pct_of_company_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.portfolio_table.setItem(row, 4, pct_of_company_item)

            # Apply row color based on trade type - only if all trades are same type
            row_color = None
            if has_buy and not has_sell:
                # All trades are buys
                row_color = buy_color
            elif has_sell and not has_buy:
                # All trades are sells
                row_color = sell_color

            # Apply row color explicitly to each cell in the first five columns
            if row_color:
                for col in range(5):  # Now includes the % of Company column
                    item = self.portfolio_table.item(row, col)
                    if item:
                        item.setBackground(QBrush(row_color))

            # Fund-specific columns
            for fund_idx, fund_name in enumerate(self.fund_names):
                base_col = len(fixed_columns) + fund_idx * len(fund_columns)

                # Get color for this fund
                color_idx = fund_idx % len(fund_colors)
                fund_color = fund_colors[color_idx]

                # Check if this specific fund has a trade for this symbol
                cell_color = fund_color
                fund_symbol_key = f"{fund_name}:{symbol}"

                if fund_symbol_key in self.proposed_executions:
                    execution = self.proposed_executions[fund_symbol_key]
                    if execution['trade_type'] == 'Buy':
                        # Use strong buy color for fund cells with buy trades
                        cell_color = buy_color
                    elif execution['trade_type'] == 'Sell':
                        # Use strong sell color for fund cells with sell trades
                        cell_color = sell_color

                if fund_name not in pos_data['funds']:
                    # Empty columns for this fund
                    for i in range(len(fund_columns)):
                        empty_item = QTableWidgetItem("")
                        empty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        # Apply fund color to empty cells
                        empty_item.setBackground(QBrush(cell_color))
                        self.portfolio_table.setItem(row, base_col + i, empty_item)
                    continue

                fund_position = pos_data['funds'][fund_name]

                # Current Rel. Weight (column 0 in fund columns)
                rel_weight_item = QTableWidgetItem(f"{fund_position['rel_weight']:.2f}x")
                rel_weight_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                rel_weight_item.setBackground(QBrush(cell_color))
                self.portfolio_table.setItem(row, base_col + 0, rel_weight_item)

                # New Rel. Weight (column 1 in fund columns)
                if fund_position.get('new_rel_weight', 0) != 0:
                    new_raw_item = QTableWidgetItem(f"{fund_position['new_rel_weight']:.2f}x")
                else:
                    new_raw_item = QTableWidgetItem("")
                new_raw_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                new_raw_item.setBackground(QBrush(cell_color))
                self.portfolio_table.setItem(row, base_col + 1, new_raw_item)

            row += 1

        # Restore selection if possible
        if selected_symbol and selected_symbol not in ["JPY", "USD"]:
            for row in range(self.portfolio_table.rowCount()):
                symbol_col = 1  # Symbol is now in column 1
                if self.portfolio_table.item(row, symbol_col) and self.portfolio_table.item(row,
                                                                                            symbol_col).text() == selected_symbol:
                    self.portfolio_table.selectRow(row)
                    break

        # Update proposed trades table
        self.update_proposed_trades_table()

        # Update total USD display
        self.update_total_usd_display()

        # Update the fund headers
        self.update_fund_headers()

        # Auto-sort if we have a sort column defined and auto-sorting is enabled
        if hasattr(self, 'sort_column') and self.sort_column and getattr(self, 'auto_sort_enabled', True):
            if hasattr(self, 'sort_reverse'):
                reverse = self.sort_reverse
            else:
                reverse = False

            # Sort the table based on the current sort column and direction
            self.sort_portfolio_table(self.sort_column)

    def update_proposed_trades_table(self):
        """Update the proposed trades table"""
        # Clear table
        self.proposed_trades_table.setRowCount(0)

        # If no trades, return
        if not self.proposed_executions:
            return

        # Organize trades by symbol
        trades_by_symbol = {}

        for key, execution in self.proposed_executions.items():
            if ':' in key:
                fund_name, symbol = key.split(':', 1)

                # Skip if symbol not in portfolio
                if symbol not in self.portfolio:
                    continue

                # Initialize symbol entry if not exists
                if symbol not in trades_by_symbol:
                    trades_by_symbol[symbol] = {
                        'name': self.portfolio[symbol]['name'] if symbol in self.portfolio else "",
                        'price': self.portfolio[symbol]['price'] if symbol in self.portfolio else 0,
                        'trade_type': execution['trade_type'],  # Will be overridden if mixed
                        'total_shares': 0,
                        'total_value_usd': 0,
                        'funds': {},
                        'trading_days': 0,
                        'total_raw': 0,
                        'fund_count': 0
                    }

                # Add fund-specific trade
                trades_by_symbol[symbol]['funds'][fund_name] = execution

                # Update totals
                if execution['trade_type'] == trades_by_symbol[symbol]['trade_type']:
                    # Same type - add to totals
                    trades_by_symbol[symbol]['total_shares'] += execution['trade_quantity']
                    trades_by_symbol[symbol]['total_value_usd'] += execution['trade_value_usd']
                else:
                    # Mixed types - need to adjust
                    if trades_by_symbol[symbol]['total_shares'] == 0:
                        # First real trade, just use this one's type
                        trades_by_symbol[symbol]['trade_type'] = execution['trade_type']
                        trades_by_symbol[symbol]['total_shares'] = execution['trade_quantity']
                        trades_by_symbol[symbol]['total_value_usd'] = execution['trade_value_usd']
                    else:
                        # Need to adjust based on which is larger
                        if execution['trade_value_usd'] > trades_by_symbol[symbol]['total_value_usd']:
                            # This execution is larger, switch to its type
                            trades_by_symbol[symbol]['trade_type'] = execution['trade_type']
                            trades_by_symbol[symbol]['total_shares'] = execution['trade_quantity'] - \
                                                                       trades_by_symbol[symbol]['total_shares']
                            trades_by_symbol[symbol]['total_value_usd'] = execution['trade_value_usd'] - \
                                                                          trades_by_symbol[symbol]['total_value_usd']
                        else:
                            # Existing total is larger, subtract this one
                            trades_by_symbol[symbol]['total_shares'] -= execution['trade_quantity']
                            trades_by_symbol[symbol]['total_value_usd'] -= execution['trade_value_usd']

                # Update trading days - use max
                if 'trading_days' in execution and execution['trading_days']:
                    trades_by_symbol[symbol]['trading_days'] = max(
                        trades_by_symbol[symbol]['trading_days'],
                        execution['trading_days']
                    )

                # Update total RAW and count for average
                trades_by_symbol[symbol]['total_raw'] += execution['target_raw']
                trades_by_symbol[symbol]['fund_count'] += 1

        # Set row height based on font size
        row_height = self.current_font_size * 2 + 10

        # Add rows to table
        row = 0
        for symbol, trade_data in trades_by_symbol.items():
            self.proposed_trades_table.insertRow(row)

            # Set row height based on font size
            self.proposed_trades_table.setRowHeight(row, row_height)

            # Only add if there's actually a trade
            if trade_data['total_shares'] == 0 and trade_data['total_value_usd'] == 0:
                continue

            # Calculate average RAW
            avg_raw = trade_data['total_raw'] / trade_data['fund_count'] if trade_data['fund_count'] > 0 else 0

            # Get target price and % to current price (use first fund that has these values)
            target_price = None
            pct_to_curr = None

            for fund_name, execution in trade_data['funds'].items():
                if 'target_price' in execution and execution['target_price'] is not None:
                    target_price = execution['target_price']
                    pct_to_curr = execution.get('pct_to_curr')
                    break

            # Determine overall color based on trade type
            color = QColor("green") if trade_data['trade_type'] == "Buy" else QColor("red")

            # Trade Type
            type_item = QTableWidgetItem(trade_data['trade_type'])
            type_item.setForeground(color)
            self.proposed_trades_table.setItem(row, 0, type_item)

            # Ticker
            ticker_item = QTableWidgetItem(symbol)
            self.proposed_trades_table.setItem(row, 1, ticker_item)

            # Name
            name_item = QTableWidgetItem(trade_data['name'])
            self.proposed_trades_table.setItem(row, 2, name_item)

            # Shares
            shares_str = f"{int(abs(trade_data['total_shares'])):,}"
            shares_item = QTableWidgetItem(shares_str)
            shares_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            shares_item.setForeground(color)
            self.proposed_trades_table.setItem(row, 3, shares_item)

            # USD Value
            value_str = f"{int(abs(trade_data['total_value_usd'])):,}"
            value_item = QTableWidgetItem(value_str)
            value_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_item.setForeground(color)
            self.proposed_trades_table.setItem(row, 4, value_item)

            # Trading Days
            days_str = f"{trade_data['trading_days']:.1f}" if trade_data['trading_days'] else ""
            days_item = QTableWidgetItem(days_str)
            days_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.proposed_trades_table.setItem(row, 5, days_item)

            # Avg Rel Weight
            raw_str = f"{avg_raw:.2f}x"
            raw_item = QTableWidgetItem(raw_str)
            raw_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.proposed_trades_table.setItem(row, 6, raw_item)

            # Target Price
            if target_price is not None:
                price_str = f"{int(target_price):,}"
                price_item = QTableWidgetItem(price_str)
                price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.proposed_trades_table.setItem(row, 7, price_item)
            else:
                self.proposed_trades_table.setItem(row, 7, QTableWidgetItem(""))

            # % to Curr Price
            if pct_to_curr is not None:
                pct_str = f"{pct_to_curr:.1f}%"
                pct_item = QTableWidgetItem(pct_str)
                pct_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.proposed_trades_table.setItem(row, 8, pct_item)
            else:
                self.proposed_trades_table.setItem(row, 8, QTableWidgetItem(""))

            row += 1

        # Adjust column widths based on font size
        font_scaling_factor = self.current_font_size / 9.0  # Scale relative to default font size

        # Set column widths
        self.proposed_trades_table.setColumnWidth(0, int(80 * font_scaling_factor))  # Trade Type
        self.proposed_trades_table.setColumnWidth(1, int(80 * font_scaling_factor))  # Ticker
        self.proposed_trades_table.setColumnWidth(2, int(150 * font_scaling_factor))  # Name
        self.proposed_trades_table.setColumnWidth(3, int(90 * font_scaling_factor))  # Shares
        self.proposed_trades_table.setColumnWidth(4, int(90 * font_scaling_factor))  # USD Value
        self.proposed_trades_table.setColumnWidth(5, int(90 * font_scaling_factor))  # Trading Days
        self.proposed_trades_table.setColumnWidth(6, int(90 * font_scaling_factor))  # Avg Rel Weight
        self.proposed_trades_table.setColumnWidth(7, int(100 * font_scaling_factor))  # Target Price
        self.proposed_trades_table.setColumnWidth(8, int(100 * font_scaling_factor))  # % to Curr Price

    def calculate_value_usd(self, value_jpy):
        """
        Utility method to reliably calculate USD value from JPY value
        """
        if self.usd_jpy_rate > 1.0:
            return value_jpy / self.usd_jpy_rate
        else:
            # Use a default rate if no valid rate is available
            return value_jpy / 100.0

    def update_total_usd_display(self):
        """Update the total USD display for proposed trades (Sells minus Buys)"""
        total_net = 0

        for key, execution in self.proposed_executions.items():
            if 'trade_value_signed' in execution:
                # Use pre-calculated signed values
                total_net += execution['trade_value_signed']
            else:
                # Calculate on the fly for backward compatibility
                if execution['trade_type'] == 'Sell':
                    total_net += execution['trade_value_usd']
                else:  # Buy
                    total_net -= execution['trade_value_usd']

        self.total_usd_label.setText(f"Net Total: ${total_net:,.2f}")

    def on_position_select(self):
        """Handle portfolio position selection"""
        selected_items = self.portfolio_table.selectedItems()
        if not selected_items:
            self.clear_position_details()
            return

        # Get the row of the first selected cell
        row = selected_items[0].row()

        # Get symbol from Symbol column (now column 1)
        symbol_item = self.portfolio_table.item(row, 1)
        if not symbol_item:
            return

        symbol = symbol_item.text()

        if symbol not in self.portfolio:
            return

        position = self.portfolio[symbol]

        # Update position details
        self.symbol_label.setText(symbol)
        self.name_label.setText(position['name'])
        self.price_label.setText(f"{position['price']:,.2f}")

        # Sum quantities across all funds
        total_quantity = 0
        for fund_name, fund_position in position['funds'].items():
            total_quantity += fund_position['quantity']

        self.quantity_label.setText(f"{total_quantity:,.2f}")

        value_jpy = position['price'] * total_quantity
        value_usd = value_jpy / self.usd_jpy_rate if self.usd_jpy_rate > 0 else 0

        # Calculate total USD value across all positions for weight calculations
        # (exclude JPY and USD positions)
        total_value_usd = 0
        regular_positions_count = 0
        for sym, pos in self.portfolio.items():
            # Skip JPY and USD for weight calculations
            if sym in ["JPY", "USD"]:
                continue

            regular_positions_count += 1
            pos_total_qty = 0
            for fund_name, fund_position in pos['funds'].items():
                pos_total_qty += fund_position['quantity']

            pos_value_usd = pos['price'] * pos_total_qty / self.usd_jpy_rate if self.usd_jpy_rate > 0 else 0
            total_value_usd += pos_value_usd

        # Calculate weight based on USD values (excluding JPY and USD positions)
        weight = (value_usd / total_value_usd * 100) if total_value_usd > 0 else 0

        # Calculate average weight and relative weight (excluding JPY and USD positions)
        avg_weight = 100.0 / regular_positions_count if regular_positions_count > 0 else 0
        rel_weight = weight / avg_weight if avg_weight > 0 else 0

        self.value_jpy_label.setText(f"{value_jpy:,.2f}")
        self.value_usd_label.setText(f"{value_usd:,.2f}")
        self.weight_label.setText(f"{weight:.2f}%")
        self.rel_weight_label.setText(f"{rel_weight:.2f}x")

    def clear_position_details(self):
        """Clear the position details display"""
        self.symbol_label.setText("")
        self.name_label.setText("")
        self.price_label.setText("")
        self.quantity_label.setText("")
        self.value_jpy_label.setText("")
        self.value_usd_label.setText("")
        self.weight_label.setText("")
        self.rel_weight_label.setText("")

    def calculate_trade(self):
        """Redirect to multi-fund trade dialog"""
        self.create_trade_dialog()

    def create_trade_dialog(self):
        """Create a dialog for proposing trades across multiple funds with filing threshold alerts"""
        # Check if a position is selected
        if not self.portfolio_table.selectionModel().hasSelection():
            QMessageBox.information(self, "Info", "Please select a position to trade")
            return

        # Get the selected position
        row = self.portfolio_table.currentRow()
        symbol_item = self.portfolio_table.item(row, 1)  # Symbol column is at index 1

        if not symbol_item:
            return

        symbol = symbol_item.text()

        if not symbol or symbol not in self.portfolio:
            return

        position = self.portfolio[symbol]
        price = position['price']

        # Get OS (outstanding shares) value for this security
        os_shares = position.get('os_shares', 0)

        # Calculate the current % of company across all funds
        total_current_shares = 0
        total_pct_of_company = 0  # Initialize for use in the UI

        for fund_name, fund_position in position['funds'].items():
            total_current_shares += fund_position['quantity']
            total_pct_of_company += fund_position.get('pct_of_company', 0)

        # Convert to percentage format with 2 decimal places
        total_pct_of_company_display = f"{total_pct_of_company * 100:.2f}%"

        # Get filing thresholds from filings data
        pct_to_next_upward = None
        pct_to_next_downward = None

        # Check if we have filings data for this symbol
        if hasattr(self, 'filings') and symbol in self.filings:
            filing_data = self.filings[symbol]
            last_filing = filing_data.get('last_filing')

            # Calculate thresholds
            if last_filing is not None:
                # % to Next Upward: (Last Filing + 1%) - Current %
                pct_to_next_upward = (last_filing + 0.01) - total_pct_of_company

                # % to Next Downward: Current % - (Last Filing - 1%)
                pct_to_next_downward = total_pct_of_company - (last_filing - 0.01)
            else:
                # If no Last Filing, use: 5% - Current %
                pct_to_next_upward = 0.05 - total_pct_of_company
                # No downward threshold when last filing is missing

        # Create the dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Create Trade for {symbol}")
        dialog.resize(600, 500)

        layout = QVBoxLayout(dialog)

        # Create a header widget with its own background
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 10, 10, 10)  # Add some padding

        # First row of header
        first_row_layout = QHBoxLayout()
        first_row_layout.addWidget(QLabel(f"Symbol: {symbol}"))
        first_row_layout.addWidget(QLabel(f"Name: {position['name']}"))
        first_row_layout.addWidget(QLabel(f"Price: {price:,.2f} JPY"))
        header_layout.addLayout(first_row_layout)

        # Second row of header with company percentage information
        second_row_layout = QHBoxLayout()

        # Current % of Company label
        current_pct_label = QLabel(f"Current % of Company: {total_pct_of_company_display}")
        second_row_layout.addWidget(current_pct_label)

        # New % of Company label - will be updated dynamically with trades
        new_pct_label = QLabel("New % of Company: -")
        second_row_layout.addWidget(new_pct_label)

        # Change % label - will be updated dynamically with trades
        change_pct_label = QLabel("Change %: -")
        second_row_layout.addWidget(change_pct_label)

        header_layout.addLayout(second_row_layout)

        # Add third row with filing thresholds if available
        if pct_to_next_upward is not None or pct_to_next_downward is not None:
            third_row_layout = QHBoxLayout()

            if pct_to_next_upward is not None:
                upward_label = QLabel(f"% to Next Upward: {pct_to_next_upward * 100:.2f}%")
                third_row_layout.addWidget(upward_label)

            if pct_to_next_downward is not None:
                downward_label = QLabel(f"% to Next Downward: {pct_to_next_downward * 100:.2f}%")
                third_row_layout.addWidget(downward_label)

            header_layout.addLayout(third_row_layout)

        # Add header widget to main layout
        layout.addWidget(header_widget)

        # Create a scroll area for funds
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        # Create a container widget for the scroll area
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Fund entries
        fund_entries = {}
        fund_position_values = {}

        # Count fixed columns in the portfolio table
        fixed_columns = 5  # Updated: Empty (row num), Symbol, Name, Price (JPY), % of Company

        # Get the current relative weights directly from the portfolio table
        for fund_idx, fund_name in enumerate(self.fund_names):
            # Calculate column index for this fund's Curr. Rel. Weight
            rel_weight_col = fixed_columns + fund_idx * 2  # Each fund has 2 columns (Curr + New)
            new_weight_col = rel_weight_col + 1  # New Rel. Weight column

            # Check if this fund has this position by looking at the table
            rel_weight_value = None
            new_weight_value = None

            # Find the appropriate row for this symbol
            for table_row in range(self.portfolio_table.rowCount()):
                if self.portfolio_table.item(table_row, 1).text() == symbol:  # Symbol is in column 1
                    # Get the Curr. Rel. Weight value directly from the table
                    rel_weight_item = self.portfolio_table.item(table_row, rel_weight_col)
                    if rel_weight_item and rel_weight_item.text():
                        # Remove the 'x' from the end and convert to float
                        rel_weight_text = rel_weight_item.text().replace('x', '')
                        try:
                            rel_weight_value = float(rel_weight_text)
                        except ValueError:
                            rel_weight_value = 0.0

                    # Get the New Rel. Weight value if it exists
                    new_weight_item = self.portfolio_table.item(table_row, new_weight_col)
                    if new_weight_item and new_weight_item.text():
                        # Remove the 'x' from the end and convert to float
                        new_weight_text = new_weight_item.text().replace('x', '')
                        try:
                            new_weight_value = float(new_weight_text)
                        except ValueError:
                            new_weight_value = 0.0

                    break

            # Skip funds that don't have this position
            if rel_weight_value is None:
                continue

            # Store the found values
            if fund_name not in fund_position_values:
                fund_position_values[fund_name] = {
                    'current_raw': rel_weight_value,
                    'new_raw': new_weight_value if new_weight_value is not None and new_weight_value > 0 else rel_weight_value
                }

                # Add additional calculations needed for trade computations
                if 'funds' in position and fund_name in position['funds']:
                    fund_position = position['funds'][fund_name]
                    quantity = fund_position['quantity']

                    # Store the quantity for later calculations
                    fund_position_values[fund_name]['quantity'] = quantity

            # Check if there's an existing trade for this fund-symbol combination
            fund_symbol_key = f"{fund_name}:{symbol}"
            if fund_symbol_key in self.proposed_executions:
                # Use the target RAW from the existing trade
                existing_target_raw = self.proposed_executions[fund_symbol_key]['target_raw']
                fund_position_values[fund_name]['new_raw'] = existing_target_raw

        # Define the function to update company percentages with filing threshold checks
        def update_company_percentages():
            """Update the company percentage labels and check filing thresholds"""
            try:
                if os_shares <= 0:
                    return  # Can't calculate without valid OS data

                # Calculate net trade across all funds
                net_trade_shares = 0

                for fund_name, entries in fund_entries.items():
                    # Skip funds with no active trade
                    if not entries['shares_label'].text():
                        continue

                    # Get trade quantity for this fund
                    try:
                        trade_quantity_str = entries['shares_label'].text().replace(",", "")
                        trade_quantity = int(trade_quantity_str) if trade_quantity_str else 0
                        net_trade_shares += trade_quantity
                    except ValueError:
                        pass

                # Calculate new total shares and new percentage
                new_total_shares = total_current_shares + net_trade_shares
                new_pct_of_company = new_total_shares / os_shares if os_shares > 0 else 0

                # Calculate the change in percentage
                pct_change = new_pct_of_company - total_pct_of_company

                # Update the labels with new values
                new_pct_label.setText(f"New % of Company: {new_pct_of_company * 100:.2f}%")

                # Format the change percentage with a sign and color
                change_pct_text = f"Change %: {pct_change * 100:+.2f}%"  # Use + sign to always show sign
                change_pct_label.setText(change_pct_text)

                # Set color based on direction of change
                if pct_change > 0:
                    change_pct_label.setStyleSheet("color: green;")
                elif pct_change < 0:
                    change_pct_label.setStyleSheet("color: red;")
                else:
                    change_pct_label.setStyleSheet("")  # Default color for no change

                # Check if this change will trigger a filing threshold
                filing_alert = False

                # Check condition 1: Change % >= % to Next Upward
                if pct_to_next_upward is not None and pct_change >= pct_to_next_upward:
                    filing_alert = True

                # Check condition 2: Change % <= % to Next Downward (only if there is a downward threshold)
                if pct_to_next_downward is not None and pct_change <= -pct_to_next_downward:
                    filing_alert = True

                # Set ONLY the header widget background color based on filing alert
                if filing_alert:
                    # Change header background to yellow (only the header, not fund frames)
                    header_widget.setStyleSheet("background-color: #FFFFC0;")  # Light yellow
                else:
                    # Reset to default background
                    header_widget.setStyleSheet("")

            except Exception as e:
                print(f"Error updating company percentage labels: {str(e)}")

        # Define a self-contained method for handling raw input changes
        def on_raw_input_changed_local(fund_name):
            """Calculate trade values when RAW input changes"""
            try:
                # Get fund data
                fund_data = fund_position_values[fund_name]
                entries = fund_entries[fund_name]

                # Get current input and current RAW
                current_raw = fund_data['current_raw']
                new_raw = entries['raw_input'].value()

                # Only calculate a trade if there's a meaningful difference between current and new RAW
                if abs(new_raw - current_raw) < 0.001:
                    # No meaningful difference - clear trade displays
                    entries['usd_display'].setText("")
                    entries['shares_label'].setText("")
                    entries['trade_type_label'].setText("")
                    entries['trade_type_label'].setStyleSheet("")
                    entries['shares_label'].setStyleSheet("")
                    entries['usd_display'].setStyleSheet("")

                    # Still update percentages
                    update_company_percentages()
                    return

                # Count securities in the portfolio with weight > 0
                securities_count = 0
                total_portfolio_jpy = 0

                for sym, pos in self.portfolio.items():
                    # Skip cash positions
                    if pos['is_cash']:
                        continue

                    if 'funds' in pos and fund_name in pos['funds']:
                        fund_pos = pos['funds'][fund_name]
                        quantity = fund_pos.get('quantity', 0)

                        if quantity > 0:
                            securities_count += 1
                            # Calculate position value in JPY
                            total_portfolio_jpy += pos['price'] * quantity

                # Calculate current position value in JPY
                current_position_jpy = price * fund_data.get('quantity', 0)

                # Calculate current weight percentage
                current_weight = (current_position_jpy / total_portfolio_jpy * 100) if total_portfolio_jpy > 0 else 0

                # Calculate average weight
                avg_weight = 100.0 / securities_count if securities_count > 0 else 0

                # Convert RAW to target weight
                target_weight = new_raw * avg_weight

                # Calculate target position value in JPY
                target_position_jpy = (target_weight / 100) * total_portfolio_jpy

                # Calculate trade value in JPY
                trade_value_jpy = target_position_jpy - current_position_jpy

                # Determine trade type
                trade_type = "Buy" if trade_value_jpy > 0 else "Sell"

                # Calculate shares directly from JPY value
                trade_quantity = round(abs(trade_value_jpy / price)) if price > 0 else 0

                # Make sure the trade direction is correct
                if trade_type == "Sell":
                    trade_quantity = -trade_quantity

                # Convert trade value to USD for display
                trade_value_usd = trade_value_jpy / self.usd_jpy_rate if self.usd_jpy_rate > 0 else 0

                # Update USD value display
                entries['usd_display'].setText(f"{abs(int(trade_value_usd)):,} USD")

                # Update calculated values display
                if abs(trade_quantity) > 0:  # Only display if we have shares to trade
                    entries['shares_label'].setText(f"{trade_quantity:,}")
                    entries['trade_type_label'].setText(trade_type)

                    # Set color based on trade type
                    color = "green" if trade_type == "Buy" else "red"
                    entries['trade_type_label'].setStyleSheet(f"color: {color};")
                    entries['shares_label'].setStyleSheet(f"color: {color};")
                    entries['usd_display'].setStyleSheet(f"color: {color};")
                else:
                    entries['shares_label'].setText("")
                    entries['trade_type_label'].setText("")
                    entries['trade_type_label'].setStyleSheet("")
                    entries['shares_label'].setStyleSheet("")
                    entries['usd_display'].setStyleSheet("")

                # Update company percentages and check filing thresholds
                update_company_percentages()

            except Exception as e:
                print(f"Error calculating values: {str(e)}")

        # Define colors for different funds
        fund_colors = [
            "rgba(230, 242, 255, 0.3)",  # Light blue
            "rgba(230, 255, 230, 0.3)",  # Light green
            "rgba(255, 242, 230, 0.3)",  # Light orange
            "rgba(242, 230, 255, 0.3)"  # Light purple
        ]

        # Create a frame for each fund
        for fund_idx, fund_name in enumerate(self.fund_names):
            # Skip if this fund doesn't have this position
            if fund_name not in fund_position_values:
                continue

            fund_data = fund_position_values[fund_name]

            # Get color for this fund
            color_idx = fund_idx % len(fund_colors)
            fund_color = fund_colors[color_idx]

            # Create a group box for this fund
            fund_group = QGroupBox(fund_name)
            fund_group.setStyleSheet(f"QGroupBox {{ background-color: {fund_color}; }}")
            fund_layout = QGridLayout(fund_group)

            # Display current RAW from our looked-up value
            fund_layout.addWidget(QLabel("Current Rel. Weight:"), 0, 0)
            current_raw_label = QLabel(f"{fund_data['current_raw']:.2f}x")
            fund_layout.addWidget(current_raw_label, 0, 1)

            # New RAW input - pre-populated with new_raw if available, or current_raw
            fund_layout.addWidget(QLabel("New Rel. Weight:"), 1, 0)
            # Use QDoubleSpinBox for spinner with smaller step increment
            raw_input = QDoubleSpinBox()
            raw_input.setRange(0, 10.0)  # Set a reasonable range
            raw_input.setDecimals(2)  # Show 2 decimal places
            raw_input.setSingleStep(0.01)  # Increment by 0.01
            raw_input.setValue(fund_data.get('new_raw', fund_data['current_raw']))  # Use new_raw if available
            fund_layout.addWidget(raw_input, 1, 1)

            # USD value display (read-only, not a user input)
            fund_layout.addWidget(QLabel("USD Value:"), 1, 2)
            usd_display = QLabel("")  # Start with empty
            fund_layout.addWidget(usd_display, 1, 3)

            # Display calculated values
            fund_layout.addWidget(QLabel("Trade Type:"), 2, 0)
            trade_type_label = QLabel("")
            fund_layout.addWidget(trade_type_label, 2, 1)

            fund_layout.addWidget(QLabel("Shares:"), 2, 2)
            shares_label = QLabel("")
            fund_layout.addWidget(shares_label, 2, 3)

            # Store references
            fund_entries[fund_name] = {
                'raw_input': raw_input,
                'usd_display': usd_display,
                'trade_type_label': trade_type_label,
                'shares_label': shares_label
            }

            # Create a function to handle value changes for this specific fund
            def create_handler(fund_name):
                def handle_value_changed(value):
                    on_raw_input_changed_local(fund_name)

                return handle_value_changed

            # Connect signal using the handler
            raw_input.valueChanged.connect(create_handler(fund_name))

            scroll_layout.addWidget(fund_group)

        # Add the scroll widget to the scroll area
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        # Add buttons at the bottom
        button_layout = QHBoxLayout()

        # Reverse the order of the Cancel and Submit buttons
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        # Add spacer to push the submit button to the right
        button_layout.addStretch()

        submit_btn = QPushButton("Submit")
        submit_btn.clicked.connect(
            lambda: self.submit_trades(dialog, symbol, fund_entries, fund_position_values)
        )
        button_layout.addWidget(submit_btn)

        layout.addLayout(button_layout)

        # Trigger calculations for initial values if there are existing trades
        for fund_name, entries in fund_entries.items():
            # Check if there's an existing trade (new_raw != current_raw)
            if abs(fund_position_values[fund_name].get('new_raw', 0) - fund_position_values[fund_name][
                'current_raw']) > 0.001:
                # Trigger the calculation
                on_raw_input_changed_local(fund_name)

        # Initialize calculations for existing trades
        for fund_name, fund_data in fund_position_values.items():
            # Check if new_raw is different from current_raw (indicating an existing trade)
            if 'new_raw' in fund_data and abs(fund_data['new_raw'] - fund_data['current_raw']) > 0.001:
                # Trigger the initial calculation to display trade details
                on_raw_input_changed_local(fund_name)

        # Initialize the percentage calculations
        update_company_percentages()

        # Show the dialog
        dialog.exec_()

    def on_raw_input_changed(self, fund_entries, fund_position_values, fund_name):
        """Improved version of on_raw_input_changed that updates company percentages correctly"""
        try:
            # Get fund data
            fund_data = fund_position_values[fund_name]
            entries = fund_entries[fund_name]

            # Get current input and current RAW
            current_raw = fund_data['current_raw']
            new_raw = entries['raw_input'].value()

            # Only calculate a trade if there's a meaningful difference between current and new RAW
            if abs(new_raw - current_raw) < 0.001:
                # No meaningful difference - clear trade displays
                entries['usd_display'].setText("")
                entries['shares_label'].setText("")
                entries['trade_type_label'].setText("")
                entries['trade_type_label'].setStyleSheet("")
                entries['shares_label'].setStyleSheet("")
                entries['usd_display'].setStyleSheet("")

                # Still update the percentage calculations in case other funds have trades
                self.update_company_percentage_labels()
                return

            # Get the symbol from the stored attribute
            symbol = self.current_trade_symbol

            # Get position information
            position = self.portfolio[symbol]
            price = position['price']  # Price in JPY

            # Count securities in the portfolio with weight > 0
            securities_count = 0
            total_portfolio_jpy = 0

            for sym, pos in self.portfolio.items():
                # Skip cash positions
                if pos['is_cash']:
                    continue

                if 'funds' in pos and fund_name in pos['funds']:
                    fund_pos = pos['funds'][fund_name]
                    quantity = fund_pos.get('quantity', 0)

                    if quantity > 0:
                        securities_count += 1
                        # Calculate position value in JPY
                        total_portfolio_jpy += pos['price'] * quantity

            # Calculate current position value in JPY
            current_position_jpy = price * fund_data.get('quantity', 0)

            # Calculate current weight percentage
            current_weight = (current_position_jpy / total_portfolio_jpy * 100) if total_portfolio_jpy > 0 else 0

            # Calculate average weight
            avg_weight = 100.0 / securities_count if securities_count > 0 else 0

            # Convert RAW to target weight
            target_weight = new_raw * avg_weight

            # Calculate target position value in JPY
            target_position_jpy = (target_weight / 100) * total_portfolio_jpy

            # Calculate trade value in JPY
            trade_value_jpy = target_position_jpy - current_position_jpy

            # Determine trade type
            trade_type = "Buy" if trade_value_jpy > 0 else "Sell"

            # Calculate shares directly from JPY value
            trade_quantity = round(abs(trade_value_jpy / price)) if price > 0 else 0

            # Make sure the trade direction is correct
            if trade_type == "Sell":
                trade_quantity = -trade_quantity

            # Convert trade value to USD for display
            trade_value_usd = trade_value_jpy / self.usd_jpy_rate if self.usd_jpy_rate > 0 else 0

            # Update USD value display
            entries['usd_display'].setText(f"{abs(int(trade_value_usd)):,} USD")

            # Update calculated values display
            if abs(trade_quantity) > 0:  # Only display if we have shares to trade
                entries['shares_label'].setText(f"{trade_quantity:,}")
                entries['trade_type_label'].setText(trade_type)

                # Set color based on trade type
                color = "green" if trade_type == "Buy" else "red"
                entries['trade_type_label'].setStyleSheet(f"color: {color};")
                entries['shares_label'].setStyleSheet(f"color: {color};")
                entries['usd_display'].setStyleSheet(f"color: {color};")
            else:
                entries['shares_label'].setText("")
                entries['trade_type_label'].setText("")
                entries['trade_type_label'].setStyleSheet("")
                entries['shares_label'].setStyleSheet("")
                entries['usd_display'].setStyleSheet("")

            # Update company percentage calculations
            self.update_company_percentage_labels()

        except Exception as e:
            print(f"Error calculating values: {str(e)}")

    def update_company_percentage_labels(self, dialog, fund_entries):
        """Update the company percentage labels using instance attributes instead of dialog properties"""
        try:
            # Get data from instance attributes
            symbol = self.current_trade_symbol
            total_current_shares = self.current_trade_total_shares
            os_shares = self.current_trade_os_shares
            total_pct_of_company = self.current_trade_total_pct
            fund_entries = self.current_trade_fund_entries

            # Add some debugging output
            print(f"DEBUG: OS shares = {os_shares}, Total current shares = {total_current_shares}")

            if not symbol or os_shares <= 0:
                print("DEBUG: Cannot calculate percentages - invalid OS data")
                return  # Can't calculate without valid OS data

            # Calculate net trade across all funds
            net_trade_shares = 0

            for fund_name, entries in fund_entries.items():
                # Skip funds with no active trade
                if not entries['shares_label'].text():
                    continue

                # Get trade quantity for this fund
                try:
                    trade_quantity_str = entries['shares_label'].text().replace(",", "")
                    trade_quantity = int(trade_quantity_str) if trade_quantity_str else 0
                    net_trade_shares += trade_quantity
                    print(f"DEBUG: Fund {fund_name} trade = {trade_quantity} shares")
                except ValueError:
                    pass

            print(f"DEBUG: Net trade = {net_trade_shares} shares")

            # Calculate new total shares and new percentage
            new_total_shares = total_current_shares + net_trade_shares
            new_pct_of_company = new_total_shares / os_shares if os_shares > 0 else 0

            print(f"DEBUG: New total = {new_total_shares} shares, New % = {new_pct_of_company * 100:.2f}%")

            # Calculate the change in percentage
            pct_change = new_pct_of_company - total_pct_of_company

            # Update the labels with new values
            if hasattr(self, 'new_pct_label'):
                new_pct_text = f"New % of Company: {new_pct_of_company * 100:.2f}%"
                self.new_pct_label.setText(new_pct_text)

            # Format the change percentage with a sign and color
            change_pct_text = f"Change %: {pct_change * 100:+.2f}%"  # Use + sign to always show sign

            if hasattr(self, 'change_pct_label'):
                self.change_pct_label.setText(change_pct_text)

                # Set color based on direction of change
                if pct_change > 0:
                    self.change_pct_label.setStyleSheet("color: green;")
                elif pct_change < 0:
                    self.change_pct_label.setStyleSheet("color: red;")
                else:
                    self.change_pct_label.setStyleSheet("")  # Default color for no change

        except Exception as e:
            print(f"Error updating company percentage labels: {str(e)}")
            import traceback
            traceback.print_exc()

    def submit_trades(self, dialog, symbol, fund_entries, fund_position_values):
        """Process and submit the proposed trades"""
        try:
            # Check if any trades were entered
            has_trades = False

            # Calculate aggregate values for display in the proposed trades table
            total_shares = 0
            total_usd_value = 0
            total_raw_value = 0
            num_funds_with_trades = 0
            trading_days_max = 0

            # Process each fund's trade
            for fund_name, entries in fund_entries.items():
                new_raw = entries['raw_input'].value()

                # Skip if no trade was calculated
                trade_type = entries['trade_type_label'].text()
                if not trade_type:
                    continue

                try:
                    # Get the trade details
                    target_raw = new_raw  # Store the target RAW

                    # Get the trade quantity from the shares label
                    trade_quantity_str = entries['shares_label'].text().replace(",", "")
                    trade_quantity = float(trade_quantity_str) if trade_quantity_str else 0

                    # Get the trade value from the USD display
                    usd_display_text = entries['usd_display'].text()
                    usd_value_str = usd_display_text.replace(",", "").replace(" USD", "")
                    trade_value_usd = float(usd_value_str) if usd_value_str else 0

                    # Skip if zero quantity/value
                    if trade_quantity == 0 or trade_value_usd == 0:
                        continue

                    # Calculate trading days if ADV exists
                    trading_days = 0
                    if symbol in self.portfolio and 'adv_10pct' in self.portfolio[symbol] and self.portfolio[symbol][
                        'adv_10pct'] > 0:
                        trading_days = round(abs(trade_value_usd) / self.portfolio[symbol]['adv_10pct'] * 10) / 10
                        trading_days_max = max(trading_days_max, trading_days)

                    # Create the fund-symbol key
                    fund_symbol_key = f"{fund_name}:{symbol}"

                    # Store for signed calculations (invert for Buy since it's negative cash flow)
                    signed_value = -trade_value_usd if trade_type == "Buy" else trade_value_usd

                    # Save to proposed executions
                    self.proposed_executions[fund_symbol_key] = {
                        'fund': fund_name,
                        'symbol': symbol,
                        'trade_type': trade_type,
                        'trade_quantity': trade_quantity,
                        'target_raw': target_raw,
                        'trade_value_usd': trade_value_usd,
                        'trade_value_signed': signed_value,
                        'trading_days': trading_days,
                        'target_price': None,
                        'pct_to_curr': None
                    }

                    # Track aggregates
                    if trade_type == "Buy":
                        total_shares += trade_quantity
                        total_usd_value -= trade_value_usd
                    else:  # Sell
                        total_shares -= trade_quantity
                        total_usd_value += trade_value_usd

                    total_raw_value += target_raw
                    num_funds_with_trades += 1
                    has_trades = True

                except ValueError as e:
                    QMessageBox.critical(self, "Error", f"Invalid input for {fund_name}: {str(e)}")
                    return

            # If no trades were entered, show message and return
            if not has_trades:
                QMessageBox.information(self, "Info", "No trades were entered")
                dialog.accept()
                return

            # Get OS shares value from portfolio
            os_shares = self.portfolio[symbol].get('os_shares', 0)

            # Calculate company percentage updates if OS is available
            if os_shares > 0:
                # Calculate current total shares across all funds
                total_current_shares = 0
                for fund_name, fund_position in self.portfolio[symbol]['funds'].items():
                    total_current_shares += fund_position['quantity']

                # Calculate new total shares after trades
                new_total_shares = total_current_shares + total_shares

                # Calculate new percentage of company
                new_pct_of_company = new_total_shares / os_shares if os_shares > 0 else 0

                # Calculate per-fund percentages based on proportion
                if new_total_shares > 0:
                    for fund_name, fund_position in self.portfolio[symbol]['funds'].items():
                        # Get current quantity for this fund
                        current_quantity = fund_position['quantity']

                        # Check if this fund has a trade
                        fund_symbol_key = f"{fund_name}:{symbol}"
                        if fund_symbol_key in self.proposed_executions:
                            # Add trade quantity to current quantity
                            trade_quantity = self.proposed_executions[fund_symbol_key]['trade_quantity']
                            new_quantity = current_quantity + trade_quantity
                        else:
                            new_quantity = current_quantity

                        # Make sure we don't divide by zero
                        if new_total_shares > 0:
                            # Calculate this fund's percentage of the new total
                            fund_proportion = new_quantity / new_total_shares
                            fund_pct_of_company = new_pct_of_company * fund_proportion

                            # Update the fund's pct_of_company value in the portfolio data
                            fund_position['pct_of_company'] = fund_pct_of_company

            # Update the portfolio first WITHOUT redrawing the table
            # Just update the data model to reflect new trades
            for fund_name, execution in self.proposed_executions.items():
                if ':' in fund_name:  # Format is "fund:symbol"
                    fund, symbol = fund_name.split(':', 1)
                    if symbol in self.portfolio and 'funds' in self.portfolio[symbol] and fund in \
                            self.portfolio[symbol]['funds']:
                        # Add the target RAW to the portfolio data
                        self.portfolio[symbol]['funds'][fund]['new_rel_weight'] = execution['target_raw']

            # Now update the UI directly without redrawing the entire table
            # Find the affected cells and update them
            for row in range(self.portfolio_table.rowCount()):
                # Get the symbol for this row
                symbol_item = self.portfolio_table.item(row, 1)  # Symbol is column 1
                if not symbol_item:
                    continue

                row_symbol = symbol_item.text()

                # Check if this symbol has any new trades
                has_buy = False
                has_sell = False

                # Check all funds for this symbol
                for fund_idx, fund_name in enumerate(self.fund_names):
                    fund_symbol_key = f"{fund_name}:{row_symbol}"

                    if fund_symbol_key in self.proposed_executions:
                        execution = self.proposed_executions[fund_symbol_key]

                        if execution['trade_type'] == 'Buy':
                            has_buy = True
                        elif execution['trade_type'] == 'Sell':
                            has_sell = True

                        # Calculate column index for the "New" column of this fund
                        fixed_columns = 5  # Updated: Empty, Symbol, Name, Price, % of Company
                        base_col = fixed_columns + fund_idx * 2  # Each fund has 2 columns
                        new_raw_col = base_col + 1  # New RAW is the second column for each fund

                        # Update the "New" cell with the target RAW
                        new_raw_item = self.portfolio_table.item(row, new_raw_col)
                        if new_raw_item:
                            new_raw_item.setText(f"{execution['target_raw']:.2f}x")

                            # Update color based on trade type
                            if execution['trade_type'] == 'Buy':
                                new_raw_item.setBackground(QBrush(QColor(150, 255, 150)))  # Green for buys
                            else:  # Sell
                                new_raw_item.setBackground(QBrush(QColor(255, 150, 150)))  # Red for sells

                # Update % of Company column for the row if it matches the symbol we just traded
                if row_symbol == symbol and os_shares > 0:
                    # Calculate the new total % of company for all funds
                    total_pct_of_company = 0
                    for fund_name, fund_position in self.portfolio[row_symbol]['funds'].items():
                        # Ensure we have a valid percentage value
                        pct_value = fund_position.get('pct_of_company', 0)
                        if pct_value is not None:  # Make sure it's not None
                            total_pct_of_company += pct_value

                    # Update the % of Company cell (column 4)
                    pct_of_company_item = self.portfolio_table.item(row, 4)  # % of Company column
                    if pct_of_company_item and total_pct_of_company is not None:  # Check both are not None
                        pct_of_company_item.setText(f"{total_pct_of_company * 100:.2f}%")

                # Update row color based on trade type (only if all trades are same type)
                if has_buy and not has_sell:
                    # All trades are buys - set row background to green
                    row_color = QColor(150, 255, 150)  # Green
                    for col in range(5):  # First 5 columns (including % of Company)
                        item = self.portfolio_table.item(row, col)
                        if item:
                            item.setBackground(QBrush(row_color))
                elif has_sell and not has_buy:
                    # All trades are sells - set row background to red
                    row_color = QColor(255, 150, 150)  # Red
                    for col in range(5):  # First 5 columns (including % of Company)
                        item = self.portfolio_table.item(row, col)
                        if item:
                            item.setBackground(QBrush(row_color))

            # Update the proposed trades table - this doesn't affect the portfolio table
            self.update_proposed_trades_table()

            # Update total USD display
            self.update_total_usd_display()

            # Update the Cash Path charts if they're currently visible
            if self.chart_visible:
                self.create_cash_path_chart()

            # Close dialog
            dialog.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error creating trades: {str(e)}")
            import traceback
            traceback.print_exc()

    def add_to_proposed_trades(self):
        """Add the calculated trade to proposed trades - now redirects to create_trade_dialog"""
        self.create_trade_dialog()

    def on_proposed_trade_select(self):
        """Enable action buttons when a proposed trade is selected"""
        if self.proposed_trades_table.selectedItems():
            self.edit_trade_btn.setEnabled(True)
            self.delete_trade_btn.setEnabled(True)
        else:
            self.edit_trade_btn.setEnabled(False)
            self.delete_trade_btn.setEnabled(False)

    def on_proposed_trade_double_click(self, row, column):
        """Handle double-click event on proposed trades table"""
        # Column 7 is "Target Price" (index 7)
        if column == 7:
            self.edit_target_price(row)

    def edit_target_price(self, row):
        """Edit target price for the selected proposed trade"""
        # Get symbol from the trade row
        symbol_item = self.proposed_trades_table.item(row, 1)  # Ticker column
        if not symbol_item:
            return

        symbol = symbol_item.text()

        # Find all fund-specific executions for this symbol
        fund_executions = {}
        for key, execution in self.proposed_executions.items():
            if ':' in key:
                fund_name, sym = key.split(':', 1)
                if sym == symbol:
                    fund_executions[fund_name] = execution

        if not fund_executions:
            return

        # For simplicity, use the price from the portfolio
        if symbol not in self.portfolio:
            return

        position = self.portfolio[symbol]
        price = position['price']

        # Create edit dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit Target Price for {symbol}")
        dialog.resize(350, 150)

        layout = QVBoxLayout(dialog)

        # Current price display
        layout.addWidget(QLabel(f"Current Price: {price:,.2f} JPY"))

        # Target price input
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Target Price:"))

        # Get current target price (if any)
        current_target_price = 0
        for fund_name, execution in fund_executions.items():
            if execution.get('target_price') is not None:
                current_target_price = execution['target_price']
                break

        # Use QSpinBox for target price to add up/down arrows
        target_price_spin = QSpinBox()
        target_price_spin.setRange(0, 1000000)  # Large range for prices
        target_price_spin.setSingleStep(100)  # Increment by 100
        if current_target_price:
            target_price_spin.setValue(int(current_target_price))

        input_layout.addWidget(target_price_spin)

        layout.addLayout(input_layout)

        # Buttons - reverse order with Cancel on left, Update on right
        button_layout = QHBoxLayout()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        # Add spacer to push the update button to the right
        button_layout.addStretch()

        update_btn = QPushButton("Update")
        update_btn.clicked.connect(
            lambda: self.update_target_price(dialog, symbol, target_price_spin.value(), fund_executions, price, row)
        )
        button_layout.addWidget(update_btn)

        layout.addLayout(button_layout)

        # Show dialog
        dialog.exec_()

    def update_target_price(self, dialog, symbol, target_price, fund_executions, price, row):
        """Update target price in the proposed executions"""
        try:
            # Validate target price
            if target_price <= 0:
                QMessageBox.critical(dialog, "Error", "Target Price must be positive")
                return

            # Update all fund-specific executions for this symbol
            for fund_name, execution in fund_executions.items():
                # Update target price
                execution['target_price'] = target_price

                # Calculate % to current price
                if target_price is not None:
                    pct_to_curr = (target_price / price - 1) * 100

                    # Adjust sign based on trade type
                    trade_type = execution['trade_type']
                    if trade_type == "Buy":
                        # For buys, we want the percentage to be negative
                        pct_to_curr = -abs(pct_to_curr)
                    else:  # Sell
                        # For sells, we want the percentage to be positive
                        pct_to_curr = abs(pct_to_curr)

                    execution['pct_to_curr'] = pct_to_curr
                else:
                    execution['pct_to_curr'] = None

            # Update the display in the proposed trades table
            # Format values
            target_price_str = f"{int(target_price):,}" if target_price is not None else ""

            # Get the first execution to determine trade type
            first_execution = next(iter(fund_executions.values()))
            trade_type = first_execution['trade_type']

            # Calculate percentage - use average if there are multiple funds
            pct_to_curr_total = 0
            pct_count = 0

            for fund_name, execution in fund_executions.items():
                if execution.get('pct_to_curr') is not None:
                    pct_to_curr_total += execution['pct_to_curr']
                    pct_count += 1

            pct_to_curr_avg = pct_to_curr_total / pct_count if pct_count > 0 else None
            pct_to_curr_str = f"{pct_to_curr_avg:.1f}%" if pct_to_curr_avg is not None else ""

            # Update the table items
            self.proposed_trades_table.item(row, 7).setText(target_price_str)  # Target Price column
            self.proposed_trades_table.item(row, 8).setText(pct_to_curr_str)  # % to Curr Price column

            # Update charts if visible
            if self.chart_visible:
                self.create_cash_path_chart()

            # Close dialog
            dialog.accept()

        except ValueError:
            QMessageBox.critical(dialog, "Error", "Please enter a valid number for Target Price")
        except Exception as e:
            QMessageBox.critical(dialog, "Error", f"Error updating Target Price: {str(e)}")

    def edit_proposed_trade(self):
        """Edit the target RAW of a selected proposed trade"""
        if not self.proposed_trades_table.selectedItems():
            return

        row = self.proposed_trades_table.currentRow()
        symbol_item = self.proposed_trades_table.item(row, 1)  # Ticker column

        if not symbol_item:
            return

        symbol = symbol_item.text()

        # Find all fund-specific executions for this symbol
        fund_executions = {}
        for key, execution in self.proposed_executions.items():
            if ':' in key:
                fund_name, sym = key.split(':', 1)
                if sym == symbol:
                    fund_executions[fund_name] = execution

        if not fund_executions:
            return

        # Create edit dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit Trade for {symbol}")
        dialog.resize(500, 400)

        layout = QVBoxLayout(dialog)

        # Create a scroll area for funds
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        # Create a container widget for the scroll area
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Store variables for each fund
        fund_entries = {}

        # Define colors for funds
        fund_colors = [
            "rgba(230, 242, 255, 0.3)",  # Light blue
            "rgba(230, 255, 230, 0.3)",  # Light green
            "rgba(255, 242, 230, 0.3)",  # Light orange
            "rgba(242, 230, 255, 0.3)"  # Light purple
        ]

        # Add a section for each fund
        for fund_idx, (fund_name, execution) in enumerate(fund_executions.items()):
            # Get color for this fund
            color_idx = fund_idx % len(fund_colors)
            fund_color = fund_colors[color_idx]

            fund_group = QGroupBox(fund_name)
            fund_group.setStyleSheet(f"QGroupBox {{ background-color: {fund_color}; }}")
            group_layout = QGridLayout(fund_group)

            # Current and new target RAW
            group_layout.addWidget(QLabel("Current Target RAW:"), 0, 0)
            group_layout.addWidget(QLabel(f"{execution['target_raw']:.2f}x"), 0, 1)

            group_layout.addWidget(QLabel("New Target RAW:"), 1, 0)
            # Use a QDoubleSpinBox for spinner up/down arrows
            raw_input = QDoubleSpinBox()
            raw_input.setRange(0, 10.0)  # Set a reasonable range
            raw_input.setDecimals(2)  # Show 2 decimal places
            raw_input.setSingleStep(0.1)  # Increment by 0.1
            raw_input.setValue(execution['target_raw'])  # Set current value
            group_layout.addWidget(raw_input, 1, 1)

            # Store variable
            fund_entries[fund_name] = {
                'raw_input': raw_input,
                'execution': execution
            }

            scroll_layout.addWidget(fund_group)

        # Add the scroll widget to the scroll area
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        # Add buttons at the bottom
        button_layout = QHBoxLayout()

        # Reverse button order - Cancel on left, Update on right
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        # Add spacer to push the update button to the right
        button_layout.addStretch()

        update_btn = QPushButton("Update")
        update_btn.clicked.connect(
            lambda: self.update_proposed_trade_raws(dialog, symbol, fund_entries, row)
        )
        button_layout.addWidget(update_btn)

        layout.addLayout(button_layout)

        # Show dialog
        dialog.exec_()

    def update_proposed_trade_raws(self, dialog, symbol, fund_entries, row):
        """Update RAW values in the proposed executions"""
        try:
            # Update each fund's trade
            changes_made = False

            for fund_name, entry_data in fund_entries.items():
                new_raw = entry_data['raw_input'].value()
                old_raw = entry_data['execution']['target_raw']

                # Skip if no change
                if abs(new_raw - old_raw) < 0.0001:
                    continue

                # Update the target RAW
                entry_data['execution']['target_raw'] = new_raw
                changes_made = True

            if not changes_made:
                dialog.accept()
                return

            # Calculate new aggregate values for the proposed trades table
            total_raw = 0
            num_funds = 0

            for fund_name, entry_data in fund_entries.items():
                total_raw += entry_data['execution']['target_raw']
                num_funds += 1

            avg_raw = total_raw / num_funds if num_funds > 0 else 0

            # Update the display in the proposed trades table
            self.proposed_trades_table.item(row, 6).setText(f"{avg_raw:.2f}x")  # Avg Rel Weight column

            # Update portfolio display
            self.refresh_portfolio_display()

            # Update charts if visible
            if self.chart_visible:
                self.create_cash_path_chart()

            # Close dialog
            dialog.accept()

        except Exception as e:
            QMessageBox.critical(dialog, "Error", f"Error updating trades: {str(e)}")

    def delete_proposed_trade(self):
        """Delete the selected proposed trade"""
        if not self.proposed_trades_table.selectedItems():
            return

        row = self.proposed_trades_table.currentRow()
        symbol_item = self.proposed_trades_table.item(row, 1)  # Ticker column

        if not symbol_item:
            return

        symbol = symbol_item.text()

        # Confirm deletion
        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete the proposed trade for {symbol}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Remove all fund-specific executions for this symbol
        keys_to_remove = []
        for key in self.proposed_executions.keys():
            if ':' in key:
                _, sym = key.split(':', 1)
                if sym == symbol:
                    keys_to_remove.append(key)
            elif key == symbol:  # Backward compatibility
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.proposed_executions[key]

        # Remove from treeview
        self.proposed_trades_table.removeRow(row)

        # Update total USD display
        self.update_total_usd_display()

        # Update portfolio display
        self.refresh_portfolio_display()

        # Update chart if visible
        if self.chart_visible:
            self.create_cash_path_chart()

        # Disable action buttons
        self.edit_trade_btn.setEnabled(False)
        self.delete_trade_btn.setEnabled(False)

    def clear_proposed_executions(self):
        """Clear all proposed executions"""
        if not self.proposed_executions:
            return

        # Confirm clearing
        reply = QMessageBox.question(
            self, "Confirm Clear All",
            "Are you sure you want to clear all proposed trades?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Remember which symbols had proposed trades so we can update just those rows
        affected_symbols = set()
        for key in self.proposed_executions.keys():
            if ':' in key:
                _, symbol = key.split(':', 1)
                affected_symbols.add(symbol)

        # Clear all executions
        self.proposed_executions = {}

        # Clear the proposed trades table
        self.proposed_trades_table.setRowCount(0)

        # Update total USD display
        self.update_total_usd_display()

        # Update only affected rows in the portfolio table instead of refreshing everything
        if affected_symbols:
            for row in range(self.portfolio_table.rowCount()):
                symbol_item = self.portfolio_table.item(row, 1)  # Symbol column
                if not symbol_item:
                    continue

                symbol = symbol_item.text()

                if symbol in affected_symbols:
                    # Clear New Rel. Weight values and reset row colors
                    for fund_idx, fund_name in enumerate(self.fund_names):
                        # Calculate column index for the "New" column of this fund
                        fixed_columns = 5  # Updated: Empty, Symbol, Name, Price, % of Company
                        base_col = fixed_columns + fund_idx * 2  # Each fund has 2 columns
                        new_raw_col = base_col + 1  # New RAW is the second column for each fund

                        # Clear the "New" cell value
                        new_raw_item = self.portfolio_table.item(row, new_raw_col)
                        if new_raw_item:
                            new_raw_item.setText("")

                            # Get the fund color to restore default background
                            color_idx = fund_idx % 4  # We have 4 fund colors
                            fund_colors = [
                                QColor(230, 242, 255),  # Light blue
                                QColor(230, 255, 230),  # Light green
                                QColor(255, 242, 230),  # Light orange
                                QColor(242, 230, 255)  # Light purple
                            ]
                            fund_color = fund_colors[color_idx]
                            new_raw_item.setBackground(QBrush(fund_color))

                    # Reset the row background color for fixed columns
                    for col in range(5):  # First 5 columns (including % of Company)
                        item = self.portfolio_table.item(row, col)
                        if item:
                            item.setBackground(QBrush(Qt.white))

        # Update chart if visible
        if self.chart_visible:
            self.create_cash_path_chart()

    def toggle_cash_path_chart(self):
        """Toggle the cash path chart visibility"""
        if self.chart_visible:
            # Hide chart
            self.chart_frame.setVisible(False)
            self.chart_visible = False
            # Update button text to show it's currently hidden
            self.cash_path_btn.setText("Show Cash Path")

            # Resize splitter to give all space to the trades table
            self.right_splitter.setSizes([1, 0])
        else:
            # Create and show chart
            self.create_cash_path_chart()
            self.chart_frame.setVisible(True)
            self.chart_visible = True
            # Update button text to show it's currently visible
            self.cash_path_btn.setText("Hide Cash Path")

            # Resize splitter to give equal space to both parts
            total_height = self.right_splitter.size().height()
            self.right_splitter.setSizes([total_height // 2, total_height // 2])

    def create_fund_cash_path_chart(self, fund_name, executions, max_days, initial_cash_usd):
        """Create a cash path chart for a specific fund with improved height utilization

        Args:
            fund_name: Name of the fund to chart
            executions: List of executions for this fund
            max_days: Maximum number of trading days to display
            initial_cash_usd: Initial cash position in USD for this fund

        Returns:
            QWidget: Chart widget
        """
        try:
            # Validate inputs to prevent errors
            if not executions or max_days <= 0:
                # Create a simple canvas with a message
                fig = Figure(figsize=(12, 4))
                ax = fig.add_subplot(111)
                ax.text(0.5, 0.5, "No valid trade data available",
                        horizontalalignment='center', verticalalignment='center')
                ax.axis('off')
                canvas = FigureCanvas(fig)
                return canvas, initial_cash_usd / 1000000, initial_cash_usd / 1000000, initial_cash_usd / 1000000

            # Limit max_days to a reasonable number to prevent memory issues
            max_days = min(max_days, 30)

            # Create figure and axes for the dual y-axis chart
            # Make it taller to use more vertical space, from 4 to 5 height
            fig = Figure(figsize=(12, 5))

            # Calculate font sizes based on the application font size with bounds
            # Scale from app font size (default 9) to matplotlib sizes
            font_scale = max(min(self.current_font_size / 9.0, 1.5), 0.7)  # Limit scaling between 0.7 and 1.5
            base_font_size = 8 * font_scale
            title_font_size = 10 * font_scale
            axis_label_size = 8 * font_scale
            tick_label_size = 7 * font_scale
            legend_font_size = 7 * font_scale

            # Set custom font sizes for this figure
            plt.rcParams.update({
                'font.size': base_font_size,
                'axes.titlesize': title_font_size,
                'axes.labelsize': axis_label_size,
                'xtick.labelsize': tick_label_size,
                'ytick.labelsize': tick_label_size,
                'legend.fontsize': legend_font_size
            })

            ax1 = fig.add_subplot(111)
            ax2 = ax1.twinx()  # Create secondary y-axis for cash position

            # Setup data for chart
            days = list(range(0, max_days + 1))  # Include day 0 for initial cash position
            daily_cash_flow = [0] * max_days  # Daily net cash flow
            cash_position = [initial_cash_usd / 1000000]  # Initial cash position in millions

            # Create a dictionary to store daily trades by symbol
            trade_series = {}

            # Generate different shades of red and green
            num_buys = sum(1 for item in executions
                           if item['execution']['trade_type'] == 'Buy'
                           and 'trading_days' in item['execution'])
            num_sells = sum(1 for item in executions
                            if item['execution']['trade_type'] == 'Sell'
                            and 'trading_days' in item['execution'])

            # Generate color palettes (limit to prevent memory issues)
            num_buys = min(num_buys, 10)  # Limit number of colors
            num_sells = min(num_sells, 10)

            buy_colors = plt.cm.Reds(np.linspace(0.4, 0.8, max(num_buys, 1)))
            sell_colors = plt.cm.Greens(np.linspace(0.4, 0.8, max(num_sells, 1)))

            buy_idx, sell_idx = 0, 0

            # Process each proposed trade for this fund
            valid_trade_count = 0
            for item in executions:
                # Validate execution data
                if 'symbol' not in item or 'execution' not in item:
                    continue

                symbol = item['symbol']
                execution = item['execution']

                if 'trading_days' not in execution or not execution['trading_days']:
                    continue

                # Validate position exists
                if symbol not in self.portfolio:
                    continue

                position = self.portfolio[symbol]
                adv_value = position.get('adv_10pct', 0)
                if adv_value <= 0:
                    continue

                # Limit values to prevent numeric issues
                trading_days = min(execution['trading_days'], max_days)
                trade_value = execution['trade_value_usd']

                # Sanity check - skip trades with extreme values
                if abs(trade_value) > 1e10:  # $10 billion limit
                    continue

                is_buy = execution['trade_type'] == 'Buy'

                # Count valid trades
                valid_trade_count += 1

                # Select color based on trade type
                if is_buy:
                    color = buy_colors[buy_idx % len(buy_colors)]
                    buy_idx += 1
                else:
                    color = sell_colors[sell_idx % len(sell_colors)]
                    sell_idx += 1

                # Create a series key for this trade
                series_key = f"{symbol}"

                # Create a series for this trade
                trade_series[series_key] = {
                    'days': [],
                    'values': [],
                    'color': color,
                    'type': execution['trade_type'],
                    'label': f"{symbol} {execution['trade_type']}"
                }

                # Calculate daily trade amounts (with safety checks)
                full_days = min(math.floor(trading_days), max_days - 1)
                last_day_fraction = max(0, min(trading_days - full_days, 1.0))
                daily_amount = adv_value / 1000000  # Daily amount in millions

                # Add full days
                for day in range(1, full_days + 1):
                    # Amount in millions USD (negative for buys, positive for sells)
                    value = -daily_amount if is_buy else daily_amount

                    trade_series[series_key]['days'].append(day)
                    trade_series[series_key]['values'].append(value)

                    # Update daily cash flow (in millions)
                    daily_cash_flow[day - 1] += value

                # Add partial day if needed
                if last_day_fraction > 0:
                    day = full_days + 1
                    remaining_value = daily_amount * last_day_fraction  # Partial day in millions
                    value = -remaining_value if is_buy else remaining_value

                    trade_series[series_key]['days'].append(day)
                    trade_series[series_key]['values'].append(value)

                    # Update daily cash flow
                    if day <= max_days:
                        daily_cash_flow[day - 1] += value

            # If no valid trades were processed, return a simple chart
            if valid_trade_count == 0:
                ax1.text(0.5, 0.5, "No valid trade data for chart",
                         horizontalalignment='center', verticalalignment='center',
                         transform=ax1.transAxes)
                ax1.axis('off')
                canvas = FigureCanvas(fig)
                return canvas, initial_cash_usd / 1000000, initial_cash_usd / 1000000, initial_cash_usd / 1000000

            # Plot each trade series as a separate bar chart
            bar_width = 0.8 / len(trade_series) if trade_series else 0.8
            legend_handles = []
            offset = -0.4 + (bar_width / 2)

            for series_key, series in trade_series.items():
                # Skip if no data
                if not series['days'] or not series['values']:
                    continue

                # Adjust bar positions for side-by-side display
                bar_positions = [day + offset for day in series['days']]

                # Plot the bars
                bars = ax1.bar(
                    bar_positions,
                    series['values'],
                    bar_width,
                    alpha=0.7,
                    color=series['color'],
                    label=series['label']
                )

                legend_handles.append(bars)
                offset += bar_width

            # Calculate cumulative cash position
            for daily_flow in daily_cash_flow:
                cash_position.append(cash_position[-1] + daily_flow)

            # Calculate minimum and ending cash position
            min_cash = min(cash_position)
            ending_cash = cash_position[-1]

            # Plot cash position line on secondary y-axis
            cash_line = ax2.plot(
                range(len(cash_position)),
                cash_position,
                'b-',
                linewidth=2,
                label='Cash Position (USD)'
            )
            legend_handles.append(cash_line[0])

            # Set axis labels
            ax1.set_xlabel('Days')
            ax2.set_ylabel('Cash Position USD (mm)')

            # Set x-axis ticks - limit to prevent overcrowding
            max_ticks = min(len(cash_position), 15)  # Limit number of ticks
            if len(cash_position) > max_ticks:
                # Use fewer ticks for many days
                tick_indices = np.linspace(0, len(cash_position) - 1, max_ticks, dtype=int)
                ax1.set_xticks(tick_indices)
                tick_labels = ['Initial' if i == 0 else str(i) for i in tick_indices]
                ax1.set_xticklabels(tick_labels)
            else:
                # Use all ticks for few days
                ax1.set_xticks(range(len(cash_position)))
                ax1.set_xticklabels(['Initial'] + [str(i) for i in range(1, len(cash_position))])

            # Add grid
            ax1.grid(True, linestyle='--', alpha=0.7)

            # Add legend - adjust columns based on font size and handle count
            # Move the legend to the bottom with more columns to save vertical space
            legend_cols = min(6, len(legend_handles))
            if self.current_font_size > 11:
                legend_cols = min(4, len(legend_handles))

            # Move legend below the chart with more columns
            fig.legend(handles=legend_handles,
                       loc='upper center',
                       bbox_to_anchor=(0.5, 0.01),  # Position very close to bottom
                       ncol=legend_cols)

            # Use tight layout with reduced padding to maximize chart area
            fig.tight_layout(rect=[0.02, 0.05, 0.98, 0.98])  # Minimal padding

            # Create canvas widget
            canvas = FigureCanvas(fig)

            return canvas, initial_cash_usd / 1000000, min_cash, ending_cash

        except Exception as e:
            # If there's any error, return a fallback chart
            print(f"Error in create_fund_cash_path_chart: {str(e)}")
            import traceback
            traceback.print_exc()

            # Create a simple error chart
            fig = Figure(figsize=(12, 4))
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, f"Error creating chart: {str(e)}",
                    horizontalalignment='center', verticalalignment='center')
            ax.axis('off')
            canvas = FigureCanvas(fig)
            return canvas, initial_cash_usd / 1000000, initial_cash_usd / 1000000, initial_cash_usd / 1000000

    def get_fund_cash_usd(self, fund_name):
        """Get cash position in USD for a specific fund (only from JPY and USD cash positions)"""
        fund_cash_usd = 0

        for symbol, position in self.portfolio.items():
            if position['is_cash'] and symbol in ['JPY', 'USD']:
                # Check if this fund has this cash position
                if 'funds' in position and fund_name in position['funds']:
                    fund_position = position['funds'][fund_name]
                    quantity = fund_position['quantity']

                    if symbol == 'JPY':
                        # For JPY cash position, convert JPY quantity to USD by dividing by the exchange rate
                        fund_cash_usd += quantity / self.usd_jpy_rate if self.usd_jpy_rate > 0 else 0
                    else:  # USD
                        # For USD cash position, the quantity is already in USD
                        fund_cash_usd += quantity  # Already in USD

        return fund_cash_usd

    def get_total_cash_usd(self):
        """Get total cash position in USD (only from JPY and USD cash positions)"""
        total_cash_usd = 0

        for symbol, position in self.portfolio.items():
            if position['is_cash'] and symbol in ['JPY', 'USD']:
                # Need to check all funds
                for fund_name, fund_position in position['funds'].items():
                    quantity = fund_position['quantity']
                    if symbol == 'JPY':
                        # For JPY cash position, convert JPY quantity to USD by dividing by the exchange rate
                        total_cash_usd += quantity / self.usd_jpy_rate if self.usd_jpy_rate > 0 else 0
                    else:  # USD
                        # For USD cash position, the quantity is already in USD
                        total_cash_usd += quantity  # Already in USD

        return total_cash_usd

    def add_position_dialog(self):
        """Open dialog to add a new position"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add New Position")
        dialog.resize(400, 350)

        layout = QVBoxLayout(dialog)

        form_layout = QGridLayout()

        # Symbol
        form_layout.addWidget(QLabel("Symbol:"), 0, 0)
        symbol_input = QLineEdit()
        form_layout.addWidget(symbol_input, 0, 1)

        # Name
        form_layout.addWidget(QLabel("Name:"), 1, 0)
        name_input = QLineEdit()
        form_layout.addWidget(name_input, 1, 1)

        # Price
        form_layout.addWidget(QLabel("Current Price (JPY):"), 2, 0)
        price_input = QLineEdit()
        form_layout.addWidget(price_input, 2, 1)

        # ADV
        form_layout.addWidget(QLabel("10% 3m ADV (USD):"), 3, 0)
        adv_input = QLineEdit("0")
        form_layout.addWidget(adv_input, 3, 1)

        # Cash position checkbox
        is_cash_check = QCheckBox("This is a cash position")
        is_cash_check.stateChanged.connect(
            lambda state: self.toggle_cash_position(state, symbol_input, name_input, price_input)
        )
        form_layout.addWidget(is_cash_check, 4, 0, 1, 2)

        # Currency radio buttons
        currency_group = QGroupBox()
        currency_layout = QHBoxLayout(currency_group)

        currency_button_group = QButtonGroup(dialog)
        jpy_radio = QRadioButton("JPY")
        jpy_radio.setChecked(True)
        usd_radio = QRadioButton("USD")

        currency_button_group.addButton(jpy_radio)
        currency_button_group.addButton(usd_radio)

        currency_layout.addWidget(jpy_radio)
        currency_layout.addWidget(usd_radio)

        form_layout.addWidget(currency_group, 5, 0, 1, 2)

        layout.addLayout(form_layout)

        # Fund selection and quantities
        if self.fund_names:
            fund_group = QGroupBox("Select Funds")
            fund_layout = QVBoxLayout(fund_group)

            fund_checks = {}
            fund_quantity_inputs = {}

            for fund_name in self.fund_names:
                fund_row = QHBoxLayout()

                # Checkbox
                fund_check = QCheckBox(fund_name)
                fund_check.setChecked(True)
                fund_row.addWidget(fund_check)

                fund_checks[fund_name] = fund_check

                # Quantity input
                fund_row.addWidget(QLabel("Quantity:"))
                # Use QSpinBox with spinner
                quantity_input = QSpinBox()
                quantity_input.setRange(0, 100000000)  # Large range for quantities
                quantity_input.setSingleStep(100)  # Increment by 100
                fund_row.addWidget(quantity_input)

                fund_quantity_inputs[fund_name] = quantity_input

                fund_layout.addLayout(fund_row)

            layout.addWidget(fund_group)
        else:
            # Create a default fund if none exists
            self.fund_names = ["Default"]

            fund_group = QGroupBox("Default Fund")
            fund_layout = QHBoxLayout(fund_group)

            fund_layout.addWidget(QLabel("Quantity:"))
            quantity_input = QSpinBox()
            quantity_input.setRange(0, 100000000)  # Large range for quantities
            quantity_input.setSingleStep(100)  # Increment by 100
            fund_layout.addWidget(quantity_input)

            fund_checks = {"Default": QCheckBox("Default")}
            fund_checks["Default"].setChecked(True)
            fund_checks["Default"].setVisible(False)  # Hide the checkbox

            fund_quantity_inputs = {"Default": quantity_input}

            layout.addWidget(fund_group)

        # Button row
        button_layout = QHBoxLayout()

        fetch_price_btn = QPushButton("Fetch Price")
        fetch_price_btn.clicked.connect(
            lambda: self.fetch_price(symbol_input.text(), price_input)
        )
        button_layout.addWidget(fetch_price_btn)

        # Reverse the button order - Cancel on left, Add on right
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        # Add spacer
        button_layout.addStretch()

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(
            lambda: self.add_position(
                symbol_input.text(),
                name_input.text(),
                price_input.text(),
                is_cash_check.isChecked(),
                dialog,
                adv_input.text(),
                "JPY" if jpy_radio.isChecked() else "USD",
                fund_checks,
                fund_quantity_inputs
            )
        )
        button_layout.addWidget(add_btn)

        layout.addLayout(button_layout)

        # Show dialog
        dialog.exec_()

    def toggle_cash_position(self, state, symbol_input, name_input, price_input):
        """Handle cash position checkbox state change"""
        if state == Qt.Checked:
            symbol_input.setText("JPY")
            name_input.setText("Japanese Yen")
            price_input.setText("1.0")
        else:
            symbol_input.setText("")
            name_input.setText("")
            price_input.setText("")

    def fetch_price(self, symbol, price_input):
        """Fetch price from YFinance for a symbol"""
        if not symbol or symbol in ["JPY", "USD"]:
            return

        try:
            # Automatically append .T for Japanese stocks
            fetch_symbol = f"{symbol}.T" if symbol not in ["JPY", "USD"] else symbol

            ticker = yf.Ticker(fetch_symbol)
            info = ticker.info
            if 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
                price_input.setText(str(info['regularMarketPrice']))
            else:
                QMessageBox.warning(self, "Warning", f"Could not fetch price for {symbol}")
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Error fetching price: {str(e)}")

    def add_position(self, symbol, name, price_str, is_cash, dialog, adv_str="0", currency="JPY", fund_checks=None,
                     fund_quantity_inputs=None):
        """Add a new position to the portfolio"""
        # Validate inputs
        if not symbol:
            QMessageBox.critical(dialog, "Error", "Symbol is required")
            return

        if not name:
            QMessageBox.critical(dialog, "Error", "Name is required")
            return

        try:
            price = float(price_str)
            if price <= 0:
                raise ValueError("Price must be positive")
        except ValueError:
            QMessageBox.critical(dialog, "Error", "Price must be a positive number")
            return

        try:
            adv_10pct = float(adv_str) if adv_str else 0
        except ValueError:
            QMessageBox.critical(dialog, "Error", "10% 3m ADV must be a number")
            return

        # Check that at least one fund is selected with a valid quantity
        if fund_checks and fund_quantity_inputs:
            has_valid_fund = False

            for fund_name, fund_check in fund_checks.items():
                if fund_check.isChecked():
                    # This fund is selected, check quantity
                    quantity = fund_quantity_inputs[fund_name].value()
                    if quantity <= 0:
                        QMessageBox.critical(dialog, "Error", f"Quantity for {fund_name} must be positive")
                        return

                    has_valid_fund = True

            if not has_valid_fund:
                QMessageBox.critical(dialog, "Error", "Please select at least one fund and provide a quantity")
                return

        # Handle cash positions
        if is_cash:
            symbol = currency  # Use the selected currency
            if currency == "JPY":
                name = "Japanese Yen"
                price = 1.0
            else:  # USD
                name = "US Dollar"
                price = self.usd_jpy_rate  # Price in JPY

        # Add position to portfolio
        self.portfolio[symbol] = {
            'name': name,
            'price': price,
            'is_cash': is_cash,
            'adv_10pct': adv_10pct,
            'currency': currency if is_cash else "JPY",
            'funds': {}  # Initialize funds dictionary
        }

        # If fund information is provided, add to each selected fund
        if fund_checks and fund_quantity_inputs:
            for fund_name, fund_check in fund_checks.items():
                if fund_check.isChecked():
                    # This fund is selected, get quantity
                    quantity = fund_quantity_inputs[fund_name].value()

                    # Add to this fund
                    self.portfolio[symbol]['funds'][fund_name] = {
                        'quantity': quantity
                    }

                    # Add fund to fund_names if it doesn't exist
                    if fund_name not in self.fund_names:
                        self.fund_names.append(fund_name)

        # Update portfolio display
        self.refresh_portfolio_display()

        # Close dialog
        dialog.accept()

    def remove_position(self):
        """Remove the selected position from the portfolio"""
        if not self.portfolio_table.selectionModel().hasSelection():
            QMessageBox.information(self, "Info", "Please select a position to remove")
            return

        row = self.portfolio_table.currentRow()
        symbol_item = self.portfolio_table.item(row, 0)

        if not symbol_item:
            return

        symbol = symbol_item.text()

        # Confirm removal
        reply = QMessageBox.question(
            self, "Confirm Removal",
            f"Are you sure you want to remove {symbol} from the portfolio?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        if symbol in self.portfolio:
            del self.portfolio[symbol]

            # Also remove any proposed executions for this symbol
            keys_to_remove = []
            for key in self.proposed_executions.keys():
                if ':' in key:
                    _, sym = key.split(':', 1)
                    if sym == symbol:
                        keys_to_remove.append(key)
                elif key == symbol:  # Backward compatibility
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self.proposed_executions[key]

            # Update displays
            self.refresh_portfolio_display()
            self.clear_position_details()

            # Update chart if visible
            if self.chart_visible:
                self.create_cash_path_chart()

    def sort_portfolio_table(self, column_index):
        """Sort the portfolio table when a column header is clicked"""
        # If already sorting by this column, reverse the order
        if self.sort_column == column_index:
            self.sort_reverse = not self.sort_reverse
        else:
            # New sort column
            self.sort_column = column_index
            self.sort_reverse = False

        # Get column header to determine sort type
        header = self.portfolio_table.horizontalHeaderItem(column_index).text()

        # Remember selected position
        selected_symbol = None
        if self.portfolio_table.selectionModel().hasSelection():
            row = self.portfolio_table.currentRow()
            symbol_item = self.portfolio_table.item(row, 1)  # Symbol is column 1
            if symbol_item:
                selected_symbol = symbol_item.text()

        # Get all data from the table and separate into regular and cash positions
        all_data = []
        regular_rows = []
        cash_rows = []

        for row in range(self.portfolio_table.rowCount()):
            row_data = []
            symbol_item = self.portfolio_table.item(row, 1)  # Symbol is column 1
            symbol = symbol_item.text() if symbol_item else ""

            for col in range(self.portfolio_table.columnCount()):
                item = self.portfolio_table.item(row, col)
                row_data.append(item.text() if item else "")

            # Store the original row data along with a flag to keep track of its type
            if symbol in ["JPY", "USD"]:
                cash_rows.append((row_data, 1 if symbol == "JPY" else 2))  # 1 for JPY, 2 for USD
            else:
                regular_rows.append(row_data)

        # Define a sort key function for regular positions
        def get_sort_key(row_data):
            value = row_data[column_index]

            # Handle empty values
            if not value:
                if "Price" in header or "Value" in header or "Weight" in header or "Quantity" in header or "% of Company" in header:
                    return 0
                return ""

            # Handle different column types
            if "Price" in header or "Value" in header:
                # Remove commas and any currency symbols
                clean_value = value.replace(",", "").replace("$", "").replace("¥", "")
                return float(clean_value) if clean_value else 0
            elif "% of Company" in header and "%" in value:
                # Extract percentage value without the % sign
                return float(value.replace("%", ""))
            elif "Weight" in header and "%" in value:
                return float(value.replace("%", ""))
            elif "Weight" in header and "x" in value:
                return float(value.replace("x", ""))
            elif "Quantity" in header or "Shares" in header:
                # Remove commas and any +/- signs
                clean_value = value.replace(",", "").replace("+", "").replace("-", "")
                return float(clean_value) if clean_value else 0
            else:
                return value

        # Sort only the regular rows based on the clicked column
        regular_rows.sort(key=get_sort_key, reverse=self.sort_reverse)

        # Combine sorted regular rows with cash rows (always at the bottom)
        # Cash rows are ordered with JPY first, then USD
        all_data = regular_rows + [data for data, _ in sorted(cash_rows, key=lambda x: x[1])]

        # Update the table with the sorted data
        self.portfolio_table.setSortingEnabled(False)  # Disable sorting to avoid recursion

        for row, row_data in enumerate(all_data):
            for col, cell_data in enumerate(row_data):
                item = self.portfolio_table.item(row, col)
                if item:
                    item.setText(cell_data)

        # Update row numbers in column 0 based on the current sorted order
        for row in range(self.portfolio_table.rowCount()):
            # Get the row number item in column 0
            row_num_item = self.portfolio_table.item(row, 0)
            if row_num_item:
                # Set the row number based on sorted position
                row_num_item.setText(str(row + 1))
                row_num_item.setTextAlignment(Qt.AlignCenter)

        self.portfolio_table.setSortingEnabled(True)  # Re-enable sorting

        # Restore selection if possible
        if selected_symbol:
            for row in range(self.portfolio_table.rowCount()):
                symbol_item = self.portfolio_table.item(row, 1)  # Symbol is column 1
                if symbol_item and symbol_item.text() == selected_symbol:
                    self.portfolio_table.selectRow(row)
                    break

    def export_proposed_trades(self):
        """Export proposed trades to Excel file"""
        if not self.proposed_executions:
            QMessageBox.information(self, "Info", "No proposed trades to export")
            return

        # Ask for file path
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        default_filename = f"proposed_trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        default_path = os.path.join(desktop_path, default_filename)

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Proposed Trades", default_path, "Excel files (*.xlsx);;All files (*.*)"
        )

        if not file_path:
            return  # User cancelled

        try:
            # Organize the trades by symbol and fund
            trades_by_symbol = {}

            for key, execution in self.proposed_executions.items():
                if ':' in key:
                    fund_name, symbol = key.split(':', 1)

                    # Initialize symbol entry if not exists
                    if symbol not in trades_by_symbol:
                        trades_by_symbol[symbol] = {
                            'name': self.portfolio[symbol]['name'] if symbol in self.portfolio else "",
                            'price': self.portfolio[symbol]['price'] if symbol in self.portfolio else 0,
                            'funds': {}
                        }

                    # Add fund-specific trade
                    trades_by_symbol[symbol]['funds'][fund_name] = execution

            # Create data for export
            data = []

            # Create records for each symbol/fund combination
            for symbol, trade_data in trades_by_symbol.items():
                position_name = trade_data['name']
                position_price = trade_data['price']

                # Add a row for each fund's trade
                for fund_name, execution in trade_data['funds'].items():
                    # Get trading days if available
                    trading_days = execution.get('trading_days', '')

                    # Get target price and % to current price
                    target_price = execution.get('target_price', None)
                    pct_to_curr = execution.get('pct_to_curr', None)

                    # Get the trade type and values
                    trade_type = execution['trade_type']
                    trade_quantity = execution['trade_quantity']
                    target_raw = execution['target_raw']

                    # Format the USD value with sign
                    usd_value = execution['trade_value_usd']
                    signed_usd_value = -usd_value if trade_type == "Buy" else usd_value

                    # Add to data
                    data.append({
                        'Fund': fund_name,
                        'Trade Type': trade_type,
                        'Symbol': symbol,
                        'Name': position_name,
                        'Price': position_price,
                        'Quantity': trade_quantity,
                        'USD Value': signed_usd_value,
                        'Trading Days': trading_days,
                        'Target RAW': target_raw,
                        'Target Price': target_price if target_price is not None else '',
                        '% to Curr Price': pct_to_curr if pct_to_curr is not None else ''
                    })

            # Create DataFrame and export
            df = pd.DataFrame(data)
            df.to_excel(file_path, index=False)

            QMessageBox.information(self, "Success", f"Proposed trades exported to {file_path}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error exporting trades: {str(e)}")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Use Fusion style for a modern look
    window = PortfolioManager()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()