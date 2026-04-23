from __future__ import annotations

import json
from datetime import date, timedelta

from stock_expert.config import Settings
from stock_expert.database import (
    get_latest_weights,
    get_latest_snapshot_id,
    get_market_snapshots_for_date,
    get_pick_results,
    get_prices_for_date,
    get_recent_price_history,
    get_review_run,
    get_top_movers,
    init_db,
    insert_review_run,
    insert_weights,
    replace_picks_for_date,
    upsert_signals,
)
from stock_expert.models import PickRow, SignalRow, Weights
from stock_expert.signals import (
    classify_risk,
    compute_fundamental_adjustment,
    compute_liquidity,
    compute_ma_trend,
    compute_medium_momentum,
    compute_momentum,
    compute_quality_adjustment,
    compute_short_momentum,
    compute_technical_adjustment,
    compute_volume_spike,
    score_signal,
)


def group_bars_by_ticker(bars):
    grouped = {}
    for bar in sorted(bars, key=lambda item: (item.ticker, item.date)):
        grouped.setdefault(bar.ticker, []).append(bar)
    return grouped


def default_weights(day: date) -> Weights:
    return Weights(date=day, momentum_weight=0.6, volume_weight=0.4)


def previous_weekday(day: date) -> date:
    previous = day - timedelta(days=1)
    while previous.weekday() >= 5:
        previous -= timedelta(days=1)
    return previous


def next_weekday(day: date) -> date:
    next_day = day + timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    return next_day


def ensure_base_state(settings: Settings, as_of: date, dry_run: bool = False) -> None:
    init_db(settings)
    latest = get_latest_weights(settings)
    if latest is None and not dry_run:
        insert_weights(settings, default_weights(as_of))


def build_signals(settings: Settings, as_of: date) -> list[SignalRow]:
    price_rows = get_recent_price_history(settings, as_of, bars=10)
    grouped_prices = group_bars_by_ticker(price_rows)
    signals: list[SignalRow] = []
    for ticker, history in grouped_prices.items():
        short_momentum = compute_short_momentum(history)
        medium_momentum = compute_medium_momentum(history)
        ma_trend = compute_ma_trend(history)
        liquidity = compute_liquidity(history, settings.low_liquidity_threshold)
        volume_spike = compute_volume_spike(history)
        signals.append(
            SignalRow(
                ticker=ticker,
                date=as_of,
                momentum=compute_momentum(history),
                volume_spike=round((0.7 * volume_spike) + (0.3 * liquidity), 4),
                short_momentum=short_momentum,
                medium_momentum=medium_momentum,
                ma_trend=ma_trend,
                liquidity=liquidity,
            )
        )
    return signals


def passes_risk_filter(settings: Settings, signal: SignalRow, as_of: date) -> bool:
    prices = group_bars_by_ticker(get_recent_price_history(settings, as_of, bars=1)).get(signal.ticker, [])
    if not prices:
        return False
    latest = prices[-1]
    traded_value = latest.close_price * latest.volume
    return traded_value >= settings.low_liquidity_threshold


def apply_same_day_chase_penalty(settings: Settings, raw_score: float, daily_change_pct: float | None) -> float:
    if daily_change_pct is None or daily_change_pct <= settings.same_day_chase_threshold_pct:
        return raw_score
    excess_pct = daily_change_pct - settings.same_day_chase_threshold_pct
    penalty = min(
        excess_pct * settings.same_day_chase_penalty_per_pct,
        settings.max_same_day_chase_penalty,
    )
    return max(raw_score - penalty, 0.0)


def generate_picks(
    settings: Settings,
    as_of: date,
    pick_count: int | None = None,
    dry_run: bool = False,
    apply_chase_penalty: bool = True,
) -> list[PickRow]:
    ensure_base_state(settings, as_of, dry_run=dry_run)
    signals = build_signals(settings, as_of)
    if not signals:
        if not dry_run:
            snapshot_id = get_latest_snapshot_id(settings, as_of)
            if snapshot_id is not None:
                replace_picks_for_date(settings, [], as_of, snapshot_id=snapshot_id)
        return []
    snapshot_id = get_latest_snapshot_id(settings, as_of)
    if snapshot_id is None:
        return []
    if not dry_run:
        upsert_signals(settings, signals, snapshot_id=snapshot_id)
    weights = get_latest_weights(settings) or default_weights(as_of)
    latest_prices = {bar.ticker: bar for bar in get_prices_for_date(settings, as_of)}
    snapshots = {item.ticker: item for item in get_market_snapshots_for_date(settings, as_of)}
    ranked: list[PickRow] = []
    for base_signal in signals:
        if not passes_risk_filter(settings, base_signal, as_of):
            continue
        snapshot = snapshots.get(base_signal.ticker)
        latest_price = latest_prices.get(base_signal.ticker)
        technical_adjustment = compute_technical_adjustment(snapshot)
        quality_adjustment = compute_quality_adjustment(snapshot, latest_price)
        fundamental_adjustment = compute_fundamental_adjustment(snapshot)
        signal = SignalRow(
            ticker=base_signal.ticker,
            date=base_signal.date,
            momentum=base_signal.momentum,
            volume_spike=base_signal.volume_spike,
            technical=technical_adjustment,
            fundamental=fundamental_adjustment,
            quality=quality_adjustment,
            short_momentum=base_signal.short_momentum,
            medium_momentum=base_signal.medium_momentum,
            ma_trend=base_signal.ma_trend,
            liquidity=base_signal.liquidity,
        )
        daily_change_pct = snapshot.daily_change_pct if snapshot else None
        score = score_signal(signal, weights) + signal.technical + signal.fundamental + signal.quality
        if apply_chase_penalty:
            score = apply_same_day_chase_penalty(settings, score, daily_change_pct)
        ranked.append(
            PickRow(
                date=as_of,
                ticker=signal.ticker,
                score=round(score, 4),
                momentum=round(signal.momentum, 4),
                volume=round(signal.volume_spike, 4),
                technical=round(signal.technical, 4),
                fundamental=round(signal.fundamental, 4),
                quality=round(signal.quality, 4),
                ma_trend=round(signal.ma_trend, 4),
                liquidity=round(signal.liquidity, 4),
                risk=classify_risk(signal.momentum, signal.volume_spike),
            )
        )
    ranked.sort(
        key=lambda row: (
            row.score,
            snapshots.get(row.ticker).daily_change_pct if row.ticker in snapshots else float("-inf"),
            (
                latest_prices[row.ticker].close_price * latest_prices[row.ticker].volume
                if row.ticker in latest_prices
                else float("-inf")
            ),
            row.momentum,
            row.volume,
        ),
        reverse=True,
    )
    limited = ranked[: (pick_count or settings.default_pick_count)]
    if not dry_run:
        replace_picks_for_date(settings, limited, as_of, snapshot_id=snapshot_id)
    return limited


def daily_summary(settings: Settings, as_of: date) -> str:
    init_db(settings)
    bars = get_prices_for_date(settings, as_of)
    snapshots = get_market_snapshots_for_date(settings, as_of)
    if not bars:
        return "\n".join(
            [
                f"Daily Market Summary - {as_of.isoformat()}",
                "Source: sqlite",
                "No market data found for this date.",
                "Import daily CSV files first with `import-daily-csv --date ...`.",
            ]
        )
    movers = sorted(bars, key=lambda row: (row.close_price - row.open_price) / row.open_price, reverse=True)
    advancers = sum(1 for row in bars if row.close_price > row.open_price)
    decliners = sum(1 for row in bars if row.close_price <= row.open_price)

    lines = [
        f"Daily Market Summary - {as_of.isoformat()}",
        "Source: sqlite",
        "Mode: imported daily CSV",
        f"Universe: {len(bars)} stocks | Advancers: {advancers} | Decliners: {decliners}",
        "",
        "Top Movers:",
    ]

    for row in movers[:5]:
        intraday_return = ((row.close_price - row.open_price) / row.open_price) * 100
        lines.append(f"- {row.ticker}: {intraday_return:+.2f}%")

    if snapshots:
        lines.append("")
        lines.append("Technical Leaders:")
        leaders = [item for item in snapshots if item.technical_daily in {"Güçlü Al", "Al"}][:5]
        if leaders:
            for item in leaders:
                lines.append(f"- {item.company_name}: {item.technical_daily}")
        else:
            lines.append("- No daily technical leaders found")

        ranked_leaders = generate_picks(settings, as_of, pick_count=3, dry_run=True)
        highlighted = [pick for pick in ranked_leaders if pick.technical > 0 or (pick.fundamental + pick.quality) > 0]
        if highlighted:
            lines.append("")
            lines.append("Signal-Ready Leaders:")
            for pick in highlighted:
                snapshot = next((item for item in snapshots if item.ticker == pick.ticker), None)
                if snapshot is None:
                    continue
                lines.append(
                    f"- {pick.ticker}: Tech {snapshot.technical_daily}/{snapshot.technical_weekly} | "
                    f"Adj {pick.technical + pick.fundamental + pick.quality:+.2f}"
                )

    return "\n".join(lines)


def picks_output(
    settings: Settings,
    as_of: date,
    dry_run: bool = False,
    apply_chase_penalty: bool = True,
) -> str:
    picks = generate_picks(settings, as_of, dry_run=dry_run, apply_chase_penalty=apply_chase_penalty)
    payload = {
        "dry_run": dry_run,
        "chase_penalty": apply_chase_penalty,
        "signal_date": as_of.isoformat(),
        "target_trade_date": next_weekday(as_of).isoformat(),
        "picks": [
            {
                "ticker": pick.ticker,
                "score": pick.score,
                "signals": {
                    "momentum": pick.momentum,
                    "volume": pick.volume,
                    "technical": pick.technical,
                    "fundamental": pick.fundamental,
                    "quality": pick.quality,
                    "ma_trend": pick.ma_trend,
                    "liquidity": pick.liquidity,
                },
                "adjustments": {
                    "technical": pick.technical,
                    "fundamental": pick.fundamental,
                    "quality": pick.quality,
                    "total_boost": round(pick.technical + pick.fundamental + pick.quality, 4),
                },
                "risk": pick.risk,
                "horizon": pick.horizon,
            }
            for pick in picks
        ],
    }
    return json.dumps(payload, indent=2)


def classify_missed_mover(settings: Settings, mover: dict[str, object]) -> tuple[str, str]:
    intraday_return = abs(float(mover["intraday_return"]))
    traded_value = float(mover["close_price"]) * float(mover["volume"])
    if traded_value < settings.low_liquidity_threshold:
        return "non_actionable", "low_liquidity"
    if intraday_return > settings.max_abs_momentum:
        return "non_actionable", "extreme_volatility"
    return "actionable", "not_selected_by_score"


def _pick_result_rows(picks: list[PickRow], prices_by_ticker: dict[str, object], target_date: date) -> list[dict[str, object]]:
    rows = []
    for pick in picks:
        price = prices_by_ticker.get(pick.ticker)
        if price is None:
            continue
        rows.append(
            {
                "signal_date": pick.date.isoformat(),
                "target_date": target_date.isoformat(),
                "ticker": pick.ticker,
                "score": pick.score,
                "open_price": price.open_price,
                "close_price": price.close_price,
            }
        )
    return rows


def review_output(
    settings: Settings,
    as_of: date,
    dry_run: bool = False,
    apply_chase_penalty: bool = True,
) -> str:
    review_date = as_of
    signal_date = previous_weekday(review_date)
    ensure_base_state(settings, as_of, dry_run=dry_run)
    generated_picks = generate_picks(
        settings,
        signal_date,
        dry_run=dry_run,
        apply_chase_penalty=apply_chase_penalty,
    )

    if dry_run:
        target_prices = {bar.ticker: bar for bar in get_prices_for_date(settings, review_date)}
        recent = _pick_result_rows(generated_picks, target_prices, review_date)
    else:
        recent = get_pick_results(settings, signal_date, review_date)
    returns = [
        (row["close_price"] - row["open_price"]) / row["open_price"]
        for row in recent
        if row["open_price"]
    ]
    avg_return = round(sum(returns) / len(returns), 4) if returns else 0.0
    win_rate = round(sum(1 for value in returns if value > 0) / len(returns), 4) if returns else 0.0

    picked_tickers = {row["ticker"] for row in recent}
    missed_top_movers = []
    missed_actionable = []
    missed_non_actionable = []
    for mover in get_top_movers(settings, review_date, 1, limit=50):
        if mover["ticker"] in picked_tickers:
            continue
        entry = {
            "ticker": mover["ticker"],
            "date": mover["date"],
            "intraday_return": round(mover["day_return"], 4),
            "close_price": round(mover["close_price"], 4),
            "volume": mover["volume"],
        }
        bucket, reason = classify_missed_mover(settings, entry)
        review_entry = {
            "ticker": entry["ticker"],
            "date": entry["date"],
            "intraday_return": entry["intraday_return"],
            "reason": reason,
        }
        missed_top_movers.append(review_entry)
        if bucket == "actionable":
            missed_actionable.append(review_entry)
        else:
            missed_non_actionable.append(review_entry)
        if len(missed_top_movers) >= 12:
            break

    current = get_latest_weights(settings) or default_weights(as_of)
    next_momentum_weight = round(min(current.momentum_weight + 0.03, 0.9), 2)
    next_volume_weight = round(max(1.0 - next_momentum_weight, 0.1), 2)
    next_weights = Weights(
        date=as_of,
        momentum_weight=next_momentum_weight,
        volume_weight=next_volume_weight,
    )
    review_run_id = None
    if not dry_run:
        existing_review = get_review_run(settings, signal_date, review_date)
        if existing_review is None:
            insert_weights(settings, next_weights)
            review_run_id = insert_review_run(
                settings=settings,
                as_of=signal_date,
                review_date=review_date,
                avg_return=avg_return,
                win_rate=win_rate,
                picks=recent,
                weights=next_weights,
            )
        else:
            review_run_id = int(existing_review["id"])
            next_weights = Weights(
                date=as_of,
                momentum_weight=existing_review["momentum_weight"],
                volume_weight=existing_review["volume_weight"],
            )

    payload = {
        "dry_run": dry_run,
        "chase_penalty": apply_chase_penalty,
        "review_run_id": review_run_id,
        "signal_date": signal_date.isoformat(),
        "review_date": review_date.isoformat(),
        "performance": {
            "avg_return": avg_return,
            "win_rate": win_rate,
        },
        "missed_top_movers": missed_top_movers,
        "missed_actionable": missed_actionable,
        "missed_non_actionable": missed_non_actionable,
        "adjustments": {
            "momentum_weight": next_weights.momentum_weight,
            "volume_weight": next_weights.volume_weight,
        },
    }
    return json.dumps(payload, indent=2)
