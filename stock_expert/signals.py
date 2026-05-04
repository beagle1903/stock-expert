from __future__ import annotations

import math
from statistics import mean

from stock_expert.models import MarketSnapshot, PriceBar, SignalRow, Weights


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _window_momentum(history: list[PriceBar], bars: int) -> float:
    if len(history) < bars:
        return 0.0
    base = history[-bars].close_price
    current = history[-1].close_price
    if base == 0:
        return 0.0
    raw = (current - base) / base
    return clamp((raw + 0.1) / 0.2)


def compute_short_momentum(history: list[PriceBar]) -> float:
    return _window_momentum(history, 4)


def compute_medium_momentum(history: list[PriceBar]) -> float:
    return _window_momentum(history, 6)


def compute_ma_trend(history: list[PriceBar]) -> float:
    if len(history) < 5:
        return 0.0
    closes = [bar.close_price for bar in history]
    short_ma = mean(closes[-3:])
    medium_ma = mean(closes[-5:])
    current = closes[-1]
    score = 0.0
    if current > medium_ma:
        score += 0.25
    if current > short_ma:
        score += 0.25
    if short_ma > medium_ma:
        score += 0.5
    return clamp(score)


def compute_momentum(history: list[PriceBar]) -> float:
    short_momentum = compute_short_momentum(history)
    medium_momentum = compute_medium_momentum(history)
    ma_trend = compute_ma_trend(history)
    return clamp((0.5 * short_momentum) + (0.25 * medium_momentum) + (0.25 * ma_trend))


def compute_volume_spike(history: list[PriceBar]) -> float:
    if len(history) < 5:
        return 0.0
    trailing = [bar.volume for bar in history[-5:-1]]
    baseline = mean(trailing) if trailing else history[-1].volume
    if baseline == 0:
        return 0.0
    ratio = history[-1].volume / baseline
    return clamp(ratio / 3)


def compute_liquidity(history: list[PriceBar], low_liquidity_threshold: float) -> float:
    if not history or low_liquidity_threshold <= 0:
        return 0.0
    latest = history[-1]
    traded_value = latest.close_price * latest.volume
    return clamp(traded_value / (low_liquidity_threshold * 5))


def classify_risk(momentum: float, volume_spike: float) -> str:
    if momentum > 0.8 or volume_spike > 0.85:
        return "high"
    if momentum > 0.5 or volume_spike > 0.5:
        return "medium"
    return "low"


def score_signal(signal: SignalRow, weights: Weights) -> float:
    return (weights.momentum_weight * signal.momentum) + (weights.volume_weight * signal.volume_spike)


def technical_label_score(label: str) -> float:
    normalized = label.strip().lower()
    mapping = {
        "guclu al": 1.0,
        "güçlü al": 1.0,
        "al": 0.5,
        "notr": 0.0,
        "nötr": 0.0,
        "sat": -0.5,
        "guclu sat": -1.0,
        "güçlü sat": -1.0,
    }
    return mapping.get(normalized, 0.0)


def compute_technical_adjustment(snapshot: MarketSnapshot | None) -> float:
    if snapshot is None:
        return 0.0
    daily_score = technical_label_score(snapshot.technical_daily)
    weekly_score = technical_label_score(snapshot.technical_weekly)
    return round(clamp((0.04 * daily_score) + (0.02 * weekly_score), -0.06, 0.06), 4)


def compute_quality_adjustment(snapshot: MarketSnapshot | None, latest_price: PriceBar | None) -> float:
    if snapshot is None or latest_price is None:
        return 0.0

    volume_ratio = 0.0
    if snapshot.avg_volume_3m > 0:
        volume_ratio = latest_price.volume / snapshot.avg_volume_3m
    volume_score = clamp(volume_ratio / 1.5)
    volume_boost = (volume_score - 0.5) * 0.04

    market_cap_boost = 0.0
    if snapshot.market_cap > 0:
        market_cap_score = clamp((math.log10(snapshot.market_cap) - 8.0) / 3.0)
        market_cap_boost = (market_cap_score - 0.5) * 0.03

    beta_boost = 0.0
    if snapshot.beta:
        beta_distance = min(abs(snapshot.beta - 1.0), 2.0)
        beta_boost = 0.015 - ((beta_distance / 2.0) * 0.03)

    return round(clamp(volume_boost + market_cap_boost + beta_boost, -0.04, 0.05), 4)


def compute_fundamental_adjustment(snapshot: MarketSnapshot | None) -> float:
    if snapshot is None:
        return 0.0

    if snapshot.pe_ratio <= 0:
        pe_boost = -0.01 if snapshot.pe_ratio < 0 else 0.0
    elif snapshot.pe_ratio <= 25:
        pe_boost = 0.02
    elif snapshot.pe_ratio <= 40:
        pe_boost = 0.005
    else:
        pe_boost = -0.01

    revenue_boost = 0.0
    if snapshot.revenue > 0:
        revenue_score = clamp((math.log10(snapshot.revenue) - 8.0) / 4.0)
        revenue_boost = revenue_score * 0.02

    return round(clamp(pe_boost + revenue_boost, -0.02, 0.04), 4)


def compute_setup_penalty(snapshot: MarketSnapshot | None, latest_price: PriceBar | None) -> float:
    if snapshot is None:
        return 0.03

    penalty = 0.0
    daily_technical = technical_label_score(snapshot.technical_daily)
    weekly_technical = technical_label_score(snapshot.technical_weekly)
    if daily_technical < 0:
        penalty += 0.03
    if weekly_technical < 0:
        penalty += 0.02
    if daily_technical < 0 and weekly_technical < 0:
        penalty += 0.02

    if snapshot.weekly_perf_pct >= 20:
        penalty += 0.015
    if snapshot.monthly_perf_pct >= 30:
        penalty += 0.015
    if snapshot.daily_change_pct >= 8 and snapshot.weekly_perf_pct >= 15:
        penalty += 0.02

    if snapshot.revenue <= 0:
        penalty += 0.025
    if snapshot.pe_ratio < 0:
        penalty += 0.025
    elif snapshot.pe_ratio > 80:
        penalty += 0.02

    if snapshot.market_cap <= 0:
        penalty += 0.02
    if snapshot.avg_volume_3m <= 0:
        penalty += 0.02

    if latest_price is not None and snapshot.avg_volume_3m > 0:
        volume_ratio = latest_price.volume / snapshot.avg_volume_3m
        if volume_ratio > 8:
            penalty += 0.02
        elif volume_ratio < 0.2:
            penalty += 0.015

    return round(clamp(penalty, 0.0, 0.12), 4)
