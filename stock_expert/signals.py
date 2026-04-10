from __future__ import annotations

from statistics import mean

from stock_expert.models import PriceBar, SignalRow, Weights


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def compute_momentum(history: list[PriceBar]) -> float:
    if len(history) < 4:
        return 0.0
    base = history[-4].close_price
    current = history[-1].close_price
    if base == 0:
        return 0.0
    raw = (current - base) / base
    return clamp((raw + 0.1) / 0.2)


def compute_volume_spike(history: list[PriceBar]) -> float:
    if len(history) < 5:
        return 0.0
    trailing = [bar.volume for bar in history[-5:-1]]
    baseline = mean(trailing) if trailing else history[-1].volume
    if baseline == 0:
        return 0.0
    ratio = history[-1].volume / baseline
    return clamp(ratio / 3)


def classify_risk(momentum: float, volume_spike: float) -> str:
    if momentum > 0.8 or volume_spike > 0.85:
        return "high"
    if momentum > 0.5 or volume_spike > 0.5:
        return "medium"
    return "low"


def score_signal(signal: SignalRow, weights: Weights) -> float:
    return (weights.momentum_weight * signal.momentum) + (weights.volume_weight * signal.volume_spike)
