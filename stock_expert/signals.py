from __future__ import annotations

from statistics import mean

from stock_expert.models import PriceBar, SignalRow, Weights


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
