"""Cash-path chart generation for Paradaim Portfolio.Tool."""

from __future__ import annotations

import math

import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from .models import Position, ProposedExecution


def build_cash_path_chart(
    fund_name: str,
    executions: list[dict],
    portfolio: dict[str, Position],
    max_days: int,
    initial_cash_usd: float,
) -> tuple[FigureCanvas, float, float, float]:
    """Create a cash-path chart widget for a single fund.

    Parameters
    ----------
    fund_name:
        Name of the fund.
    executions:
        List of ``{"symbol": str, "execution": ProposedExecution}`` dicts.
    portfolio:
        Full portfolio mapping.
    max_days:
        Maximum trading days for the x-axis.
    initial_cash_usd:
        Starting cash in USD.

    Returns
    -------
    (canvas, current_cash_mm, min_cash_mm, ending_cash_mm)
    """
    fig = Figure(figsize=(12, 4))
    ax1 = fig.add_subplot(111)
    ax2 = ax1.twinx()

    daily_cash_flow = [0.0] * max_days
    cash_position = [initial_cash_usd / 1_000_000]

    trade_series: dict[str, dict] = {}

    num_buys = sum(
        1
        for item in executions
        if item["execution"].trade_type == "Buy" and item["execution"].trading_days
    )
    num_sells = sum(
        1
        for item in executions
        if item["execution"].trade_type == "Sell" and item["execution"].trading_days
    )

    import matplotlib.pyplot as plt

    buy_colors = plt.cm.Reds(np.linspace(0.4, 0.8, max(num_buys, 1)))
    sell_colors = plt.cm.Greens(np.linspace(0.4, 0.8, max(num_sells, 1)))
    buy_idx = sell_idx = 0

    for item in executions:
        symbol = item["symbol"]
        execution: ProposedExecution = item["execution"]

        if not execution.trading_days:
            continue
        if symbol not in portfolio:
            continue

        position = portfolio[symbol]
        adv_value = position.adv_10pct
        if adv_value <= 0:
            continue

        is_buy = execution.trade_type == "Buy"

        if is_buy:
            color = buy_colors[buy_idx % len(buy_colors)]
            buy_idx += 1
        else:
            color = sell_colors[sell_idx % len(sell_colors)]
            sell_idx += 1

        series_key = symbol
        trade_series[series_key] = {
            "days": [],
            "values": [],
            "color": color,
            "label": f"{symbol} {execution.trade_type}",
        }

        full_days = math.floor(execution.trading_days)
        last_day_fraction = execution.trading_days - full_days
        daily_amount = adv_value / 1_000_000

        for day in range(1, full_days + 1):
            value = -daily_amount if is_buy else daily_amount
            trade_series[series_key]["days"].append(day)
            trade_series[series_key]["values"].append(value)
            daily_cash_flow[day - 1] += value

        if last_day_fraction > 0:
            day = full_days + 1
            remaining = daily_amount * last_day_fraction
            value = -remaining if is_buy else remaining
            trade_series[series_key]["days"].append(day)
            trade_series[series_key]["values"].append(value)
            if day - 1 < len(daily_cash_flow):
                daily_cash_flow[day - 1] += value

    bar_width = 0.8 / max(len(trade_series), 1)
    legend_handles = []
    offset = -0.4 + bar_width / 2

    for series in trade_series.values():
        bar_positions = [d + offset for d in series["days"]]
        bars = ax1.bar(
            bar_positions,
            series["values"],
            bar_width,
            alpha=0.7,
            color=series["color"],
            label=series["label"],
        )
        legend_handles.append(bars)
        offset += bar_width

    for flow in daily_cash_flow:
        cash_position.append(cash_position[-1] + flow)

    min_cash = min(cash_position)
    ending_cash = cash_position[-1]

    cash_line = ax2.plot(
        range(len(cash_position)),
        cash_position,
        "b-",
        linewidth=2,
        label="Cash Position (USD)",
    )
    legend_handles.append(cash_line[0])

    ax1.set_xlabel("Days", fontsize=8)
    ax2.set_ylabel("Cash Position USD (mm)", fontsize=8)
    ax1.set_xticks(range(len(cash_position)))
    ax1.set_xticklabels(
        ["Initial"] + [str(i) for i in range(1, len(cash_position))],
        fontsize=7,
    )
    ax1.tick_params(axis="y", labelsize=7)
    ax2.tick_params(axis="y", labelsize=7)
    ax1.grid(True, linestyle="--", alpha=0.7)

    fig.legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.02),
        ncol=min(6, len(legend_handles)),
        fontsize=7,
    )
    fig.tight_layout(rect=[0, 0.05, 1, 0.95])

    canvas = FigureCanvas(fig)
    return canvas, initial_cash_usd / 1_000_000, min_cash, ending_cash
