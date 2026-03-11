"""Schedule computation for subscription/redemption – no GUI dependencies."""

from __future__ import annotations

from .models import CASH_SYMBOLS, DEFAULT_EXCHANGE_RATE, Position


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
            "total_quantity": total_qty,
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
            "total_quantity": p["total_quantity"],
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
