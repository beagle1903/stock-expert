from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta

from stock_expert.config import Settings
from stock_expert.constants import MIN_DAILY_WIN_RETURN
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
    compute_setup_penalty,
    compute_short_momentum,
    compute_technical_adjustment,
    compute_volume_spike,
    score_signal,
)

USER_CONFIRMED_MARKET_HOLIDAYS = {
    date(2026, 5, 1),
}


def group_bars_by_ticker(bars):
    grouped = {}
    for bar in sorted(bars, key=lambda item: (item.ticker, item.date)):
        grouped.setdefault(bar.ticker, []).append(bar)
    return grouped


def default_weights(day: date) -> Weights:
    return Weights(date=day, momentum_weight=0.6, volume_weight=0.4)


def previous_weekday(day: date) -> date:
    previous = day - timedelta(days=1)
    while previous.weekday() >= 5 or previous in USER_CONFIRMED_MARKET_HOLIDAYS:
        previous -= timedelta(days=1)
    return previous


def next_weekday(day: date) -> date:
    next_day = day + timedelta(days=1)
    while next_day.weekday() >= 5 or next_day in USER_CONFIRMED_MARKET_HOLIDAYS:
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


def passes_risk_filter(settings: Settings, signal: SignalRow, as_of: date, latest_price=None) -> bool:
    if latest_price is None:
        prices = group_bars_by_ticker(get_recent_price_history(settings, as_of, bars=1)).get(signal.ticker, [])
        latest_price = prices[-1] if prices else None
    if latest_price is None:
        return False
    traded_value = latest_price.close_price * latest_price.volume
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


def cap_setup_penalty_for_strong_momentum(signal: SignalRow, setup_penalty: float) -> float:
    if signal.momentum >= 0.9 and signal.technical >= 0.06 and signal.liquidity >= 1.0:
        return min(setup_penalty, 0.03)
    return setup_penalty


def _with_selection_bucket(pick: PickRow, bucket: str) -> PickRow:
    return replace(pick, selection_bucket=bucket)


def _select_bucketed_picks(
    ranked: list[PickRow],
    snapshots: dict[str, object],
    pick_count: int,
) -> list[PickRow]:
    selected: list[PickRow] = []
    selected_tickers: set[str] = set()

    def add(candidates: list[PickRow], bucket: str, limit: int) -> None:
        for pick in candidates:
            if len([item for item in selected if item.selection_bucket == bucket]) >= limit:
                return
            if pick.ticker in selected_tickers:
                continue
            selected.append(_with_selection_bucket(pick, bucket))
            selected_tickers.add(pick.ticker)
            if len(selected) >= pick_count:
                return

    core_candidates = [
        pick
        for pick in ranked
        if pick.momentum >= 0.85 and pick.volume >= 0.85 and pick.setup_penalty <= 0.03
    ]
    add(core_candidates, "core_momentum", 2)

    breakout_candidates = sorted(
        [
            pick
            for pick in ranked
            if pick.technical >= 0.06 and pick.momentum >= 0.85 and pick.liquidity >= 1.0
        ],
        key=lambda pick: (
            snapshots.get(pick.ticker).daily_change_pct if pick.ticker in snapshots else float("-inf"),
            pick.score,
        ),
        reverse=True,
    )
    add(breakout_candidates, "breakout_technical", 2)

    recovery_candidates = sorted(
        [
            pick
            for pick in ranked
            if pick.momentum >= 0.7 and pick.volume >= 0.5 and pick.technical >= 0.03
        ],
        key=lambda pick: (
            snapshots.get(pick.ticker).daily_change_pct if pick.ticker in snapshots else float("-inf"),
            pick.score,
        ),
        reverse=True,
    )
    add(recovery_candidates, "coverage_recovery", 1)

    add(ranked, "score_fill", pick_count)
    return selected[:pick_count]


def _ranked_candidate_rows(
    settings: Settings,
    as_of: date,
    apply_chase_penalty: bool = True,
) -> tuple[list[PickRow], list[SignalRow], int | None]:
    signals = build_signals(settings, as_of)
    if not signals:
        return [], signals, get_latest_snapshot_id(settings, as_of)
    snapshot_id = get_latest_snapshot_id(settings, as_of)
    if snapshot_id is None:
        return [], signals, None
    weights = get_latest_weights(settings) or default_weights(as_of)
    latest_prices = {bar.ticker: bar for bar in get_prices_for_date(settings, as_of)}
    snapshots = {item.ticker: item for item in get_market_snapshots_for_date(settings, as_of)}
    ranked: list[PickRow] = []
    for base_signal in signals:
        snapshot = snapshots.get(base_signal.ticker)
        latest_price = latest_prices.get(base_signal.ticker)
        if not passes_risk_filter(settings, base_signal, as_of, latest_price=latest_price):
            continue
        technical_adjustment = compute_technical_adjustment(snapshot)
        quality_adjustment = compute_quality_adjustment(snapshot, latest_price)
        fundamental_adjustment = compute_fundamental_adjustment(snapshot)
        setup_penalty = cap_setup_penalty_for_strong_momentum(
            SignalRow(
                ticker=base_signal.ticker,
                date=base_signal.date,
                momentum=base_signal.momentum,
                volume_spike=base_signal.volume_spike,
                technical=technical_adjustment,
                liquidity=base_signal.liquidity,
            ),
            compute_setup_penalty(snapshot, latest_price),
        )
        signal = SignalRow(
            ticker=base_signal.ticker,
            date=base_signal.date,
            momentum=base_signal.momentum,
            volume_spike=base_signal.volume_spike,
            technical=technical_adjustment,
            fundamental=fundamental_adjustment,
            quality=quality_adjustment,
            setup_penalty=setup_penalty,
            short_momentum=base_signal.short_momentum,
            medium_momentum=base_signal.medium_momentum,
            ma_trend=base_signal.ma_trend,
            liquidity=base_signal.liquidity,
        )
        daily_change_pct = snapshot.daily_change_pct if snapshot else None
        score = score_signal(signal, weights) + signal.technical + signal.fundamental + signal.quality - signal.setup_penalty
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
                setup_penalty=round(signal.setup_penalty, 4),
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
    return ranked, signals, snapshot_id


def rank_candidates(
    settings: Settings,
    as_of: date,
    apply_chase_penalty: bool = True,
) -> list[PickRow]:
    init_db(settings)
    ranked, _, _ = _ranked_candidate_rows(settings, as_of, apply_chase_penalty)
    return ranked


def generate_picks(
    settings: Settings,
    as_of: date,
    pick_count: int | None = None,
    dry_run: bool = False,
    apply_chase_penalty: bool = True,
) -> list[PickRow]:
    ensure_base_state(settings, as_of, dry_run=dry_run)
    ranked, signals, snapshot_id = _ranked_candidate_rows(settings, as_of, apply_chase_penalty)
    if not signals:
        if not dry_run and snapshot_id is not None:
            replace_picks_for_date(settings, [], as_of, snapshot_id=snapshot_id)
        return []
    if snapshot_id is None:
        return []
    if not dry_run:
        upsert_signals(settings, signals, snapshot_id=snapshot_id)
    final_pick_count = pick_count or settings.default_pick_count
    limited = [_with_selection_bucket(pick, "score_ranked") for pick in ranked[:final_pick_count]]
    if not dry_run:
        replace_picks_for_date(settings, limited, as_of, snapshot_id=snapshot_id)
    return limited


def generate_bucketed_picks(
    settings: Settings,
    as_of: date,
    pick_count: int | None = None,
    apply_chase_penalty: bool = True,
) -> list[PickRow]:
    ensure_base_state(settings, as_of, dry_run=True)
    ranked, signals, snapshot_id = _ranked_candidate_rows(settings, as_of, apply_chase_penalty)
    if not signals or snapshot_id is None:
        return []
    snapshots = {item.ticker: item for item in get_market_snapshots_for_date(settings, as_of)}
    return _select_bucketed_picks(ranked, snapshots, pick_count or settings.default_pick_count)


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
        "Price Basis: previous close to latest price for CSV imports",
        f"Universe: {len(bars)} stocks | Advancers: {advancers} | Decliners: {decliners}",
        "",
        "Top Close Changes:",
    ]

    for row in movers[:5]:
        close_change = ((row.close_price - row.open_price) / row.open_price) * 100
        lines.append(f"- {row.ticker}: {close_change:+.2f}%")

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
                    "setup_penalty": pick.setup_penalty,
                    "ma_trend": pick.ma_trend,
                    "liquidity": pick.liquidity,
                },
                "adjustments": {
                    "technical": pick.technical,
                    "fundamental": pick.fundamental,
                    "quality": pick.quality,
                    "setup_penalty": pick.setup_penalty,
                    "total_boost": round(pick.technical + pick.fundamental + pick.quality, 4),
                    "net_adjustment": round(pick.technical + pick.fundamental + pick.quality - pick.setup_penalty, 4),
                },
                "selection_bucket": pick.selection_bucket,
                "risk": pick.risk,
                "horizon": pick.horizon,
            }
            for pick in picks
        ],
    }
    return json.dumps(payload, indent=2)


def _pick_summary(pick: PickRow, rank: int) -> dict[str, object]:
    return {
        "ticker": pick.ticker,
        "rank": rank,
        "score": pick.score,
        "setup_penalty": pick.setup_penalty,
        "net_adjustment": round(pick.technical + pick.fundamental + pick.quality - pick.setup_penalty, 4),
        "momentum": pick.momentum,
        "volume": pick.volume,
        "selection_bucket": pick.selection_bucket,
    }


def pick_disagreement_output(settings: Settings, as_of: date) -> str:
    normal_picks = generate_picks(settings, as_of, dry_run=True, apply_chase_penalty=True)
    no_chase_picks = generate_picks(settings, as_of, dry_run=True, apply_chase_penalty=False)
    normal_by_ticker = {pick.ticker: (rank, pick) for rank, pick in enumerate(normal_picks, start=1)}
    no_chase_by_ticker = {pick.ticker: (rank, pick) for rank, pick in enumerate(no_chase_picks, start=1)}
    normal_tickers = set(normal_by_ticker)
    no_chase_tickers = set(no_chase_by_ticker)
    shared_tickers = normal_tickers & no_chase_tickers
    pick_count = max(len(normal_picks), len(no_chase_picks))

    payload = {
        "signal_date": as_of.isoformat(),
        "target_trade_date": next_weekday(as_of).isoformat(),
        "normal_chase_penalty": True,
        "no_chase_penalty": False,
        "overlap": {
            "shared_count": len(shared_tickers),
            "pick_count": pick_count,
            "shared_rate": round(len(shared_tickers) / pick_count, 4) if pick_count else 0.0,
        },
        "shared_picks": [
            {
                "ticker": ticker,
                "normal_rank": normal_by_ticker[ticker][0],
                "no_chase_rank": no_chase_by_ticker[ticker][0],
                "normal_score": normal_by_ticker[ticker][1].score,
                "no_chase_score": no_chase_by_ticker[ticker][1].score,
                "setup_penalty": normal_by_ticker[ticker][1].setup_penalty,
            }
            for ticker in sorted(shared_tickers, key=lambda item: normal_by_ticker[item][0])
        ],
        "normal_only": [
            _pick_summary(pick, rank)
            for ticker, (rank, pick) in normal_by_ticker.items()
            if ticker not in no_chase_tickers
        ],
        "no_chase_only": [
            _pick_summary(pick, rank)
            for ticker, (rank, pick) in no_chase_by_ticker.items()
            if ticker not in normal_tickers
        ],
        "selection_note": "Reporting only; persisted picks still use normal chase-penalty ranking.",
    }
    return json.dumps(payload, indent=2)


def _strategy_review_summary(
    name: str,
    picks: list[PickRow],
    prices_by_ticker: dict[str, object],
) -> dict[str, object]:
    rows = []
    returns = []
    for pick in picks:
        price = prices_by_ticker.get(pick.ticker)
        return_pct = None
        won = None
        if price is not None and price.open_price:
            return_pct = (price.close_price - price.open_price) / price.open_price
            won = return_pct >= MIN_DAILY_WIN_RETURN
            returns.append(return_pct)
        rows.append(
            {
                "ticker": pick.ticker,
                "score": pick.score,
                "selection_bucket": pick.selection_bucket,
                "return": round(return_pct, 4) if return_pct is not None else None,
                "won": won,
            }
        )
    wins = sum(1 for value in returns if value >= MIN_DAILY_WIN_RETURN)
    return {
        "strategy": name,
        "pick_count": len(rows),
        "evaluated_count": len(returns),
        "wins": wins,
        "avg_return": round(sum(returns) / len(returns), 4) if returns else 0.0,
        "win_rate": round(wins / len(returns), 4) if returns else 0.0,
        "picks": rows,
    }


def bucketed_strategy_comparison_output(
    settings: Settings,
    review_date: date,
    apply_chase_penalty: bool = True,
) -> str:
    signal_date = previous_weekday(review_date)
    score_picks = generate_picks(
        settings,
        signal_date,
        dry_run=True,
        apply_chase_penalty=apply_chase_penalty,
    )
    bucketed_picks = generate_bucketed_picks(
        settings,
        signal_date,
        apply_chase_penalty=apply_chase_penalty,
    )
    prices_by_ticker = {bar.ticker: bar for bar in get_prices_for_date(settings, review_date)}
    score_tickers = {pick.ticker for pick in score_picks}
    bucketed_tickers = {pick.ticker for pick in bucketed_picks}
    payload = {
        "dry_run": True,
        "chase_penalty": apply_chase_penalty,
        "signal_date": signal_date.isoformat(),
        "review_date": review_date.isoformat(),
        "min_win_return": MIN_DAILY_WIN_RETURN,
        "strategies": [
            _strategy_review_summary("score_ranked", score_picks, prices_by_ticker),
            _strategy_review_summary("bucketed", bucketed_picks, prices_by_ticker),
        ],
        "overlap": {
            "shared_count": len(score_tickers & bucketed_tickers),
            "score_ranked_only": sorted(score_tickers - bucketed_tickers),
            "bucketed_only": sorted(bucketed_tickers - score_tickers),
        },
        "selection_note": "Reporting only; persisted picks use score_ranked selection.",
    }
    return json.dumps(payload, indent=2)


def classify_missed_mover(settings: Settings, mover: dict[str, object]) -> tuple[str, str]:
    close_change_return = abs(float(mover["close_change_return"]))
    traded_value = float(mover["close_price"]) * float(mover["volume"])
    if traded_value < settings.low_liquidity_threshold:
        return "non_actionable", "low_liquidity"
    if close_change_return > settings.max_abs_momentum:
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
                "selection_bucket": pick.selection_bucket,
                "open_price": price.open_price,
                "close_price": price.close_price,
            }
        )
    return rows


def _candidate_rankings(
    settings: Settings,
    signal_date: date,
    apply_chase_penalty: bool,
) -> dict[str, tuple[int, PickRow]]:
    candidates = rank_candidates(settings, signal_date, apply_chase_penalty=apply_chase_penalty)
    return {pick.ticker: (rank, pick) for rank, pick in enumerate(candidates, start=1)}


def _attribution_for_pick(settings: Settings, candidate: tuple[int, PickRow] | None) -> dict[str, object]:
    if candidate is None:
        return {
            "data_status": "not_in_current_ranked_candidates",
            "candidate_rank": None,
            "selection_note": "No recomputed candidate in the signal-date top ranks; check price history, liquidity filters, mapping, or ranking cutoff.",
        }

    rank, pick = candidate
    note = "inside_top_pick_cutoff" if rank <= settings.default_pick_count else "below_top_pick_cutoff"
    if pick.setup_penalty > 0:
        note = "penalized_by_setup_context"
    return {
        "data_status": "ranked_candidate",
        "candidate_rank": rank,
        "selection_note": note,
        "signals": {
            "momentum": pick.momentum,
            "volume": pick.volume,
            "technical": pick.technical,
            "fundamental": pick.fundamental,
            "quality": pick.quality,
            "setup_penalty": pick.setup_penalty,
            "ma_trend": pick.ma_trend,
            "liquidity": pick.liquidity,
        },
        "adjustments": {
            "total_boost": round(pick.technical + pick.fundamental + pick.quality, 4),
            "net_adjustment": round(pick.technical + pick.fundamental + pick.quality - pick.setup_penalty, 4),
        },
        "selection_bucket": pick.selection_bucket,
    }


def _reviewed_pick_entries(
    settings: Settings,
    rows: list[dict[str, object]],
    candidate_rankings: dict[str, tuple[int, PickRow]],
) -> list[dict[str, object]]:
    entries = []
    for row in rows:
        open_price = float(row["open_price"])
        close_price = float(row["close_price"])
        return_pct = (close_price - open_price) / open_price if open_price else 0.0
        entries.append(
            {
                "ticker": row["ticker"],
                "score": round(float(row["score"]), 4),
                "selection_bucket": row.get("selection_bucket", "unknown") if isinstance(row, dict) else "unknown",
                "return": round(return_pct, 4),
                "won": return_pct >= MIN_DAILY_WIN_RETURN,
                "attribution": _attribution_for_pick(settings, candidate_rankings.get(row["ticker"])),
            }
        )
    return entries


def next_review_weights(current: Weights, avg_return: float, win_rate: float, missed_actionable_count: int) -> Weights:
    momentum = current.momentum_weight
    if avg_return > 0 and win_rate >= 0.6:
        momentum += 0.02
    elif avg_return < 0 or win_rate < 0.4:
        momentum -= 0.03

    if missed_actionable_count >= 5:
        momentum -= 0.02
    elif missed_actionable_count <= 1 and avg_return > 0:
        momentum += 0.01

    momentum = round(min(max(momentum, 0.4), 0.8), 2)
    return Weights(
        date=current.date,
        momentum_weight=momentum,
        volume_weight=round(1.0 - momentum, 2),
    )


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
    recent_rows = [dict(row) for row in recent]
    candidate_rankings = _candidate_rankings(settings, signal_date, apply_chase_penalty)
    returns = [
        (row["close_price"] - row["open_price"]) / row["open_price"]
        for row in recent_rows
        if row["open_price"]
    ]
    avg_return = round(sum(returns) / len(returns), 4) if returns else 0.0
    win_rate = round(sum(1 for value in returns if value >= MIN_DAILY_WIN_RETURN) / len(returns), 4) if returns else 0.0
    wins = sum(1 for value in returns if value >= MIN_DAILY_WIN_RETURN)

    picked_tickers = {row["ticker"] for row in recent_rows}
    missed_top_movers = []
    missed_actionable = []
    missed_non_actionable = []
    for mover in get_top_movers(settings, review_date, 1, limit=50):
        if mover["ticker"] in picked_tickers:
            continue
        entry = {
            "ticker": mover["ticker"],
            "date": mover["date"],
            "close_change_return": round(mover["day_return"], 4),
            "close_price": round(mover["close_price"], 4),
            "volume": mover["volume"],
        }
        bucket, reason = classify_missed_mover(settings, entry)
        review_entry = {
            "ticker": entry["ticker"],
            "date": entry["date"],
            "close_change_return": entry["close_change_return"],
            "reason": reason,
            "attribution": _attribution_for_pick(settings, candidate_rankings.get(entry["ticker"])),
        }
        missed_top_movers.append(review_entry)
        if bucket == "actionable":
            missed_actionable.append(review_entry)
        else:
            missed_non_actionable.append(review_entry)
        if len(missed_top_movers) >= 12:
            break

    current = get_latest_weights(settings) or default_weights(as_of)
    if recent_rows:
        next_weights = next_review_weights(
            Weights(date=as_of, momentum_weight=current.momentum_weight, volume_weight=current.volume_weight),
            avg_return=avg_return,
            win_rate=win_rate,
            missed_actionable_count=len(missed_actionable),
        )
    else:
        next_weights = Weights(
            date=as_of,
            momentum_weight=current.momentum_weight,
            volume_weight=current.volume_weight,
        )
    review_run_id = None
    if not dry_run and recent_rows:
        existing_review = get_review_run(settings, signal_date, review_date)
        if existing_review is None:
            insert_weights(settings, next_weights)
            review_run_id = insert_review_run(
                settings=settings,
                as_of=signal_date,
                review_date=review_date,
                avg_return=avg_return,
                win_rate=win_rate,
                picks=recent_rows,
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
            "evaluation_status": "evaluated" if recent_rows else "no_prior_picks",
            "note": None if recent_rows else "No persisted picks were available for the signal date, so avg_return and win_rate are not strategy evidence.",
            "pick_count": len(recent_rows),
            "wins": wins,
            "avg_return": avg_return,
            "win_rate": win_rate,
            "min_win_return": MIN_DAILY_WIN_RETURN,
            "price_basis": "stored open_price; daily_csv imports use previous_close_to_last",
        },
        "reviewed_picks": _reviewed_pick_entries(settings, recent_rows, candidate_rankings),
        "missed_top_movers": missed_top_movers,
        "missed_actionable": missed_actionable,
        "missed_non_actionable": missed_non_actionable,
        "adjustments": {
            "momentum_weight": next_weights.momentum_weight,
            "volume_weight": next_weights.volume_weight,
        },
    }
    return json.dumps(payload, indent=2)
