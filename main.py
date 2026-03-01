#!/usr/bin/env python3
"""Taiyo PMT Trading V2 - Standalone entry point."""

import sys

from PyQt5.QtWidgets import QApplication

from taiyo_pmt.main_window import PortfolioManager


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = PortfolioManager()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
