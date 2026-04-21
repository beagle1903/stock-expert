from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PriceBar:
    ticker: str
    date: date
    open_price: float
    close_price: float
    volume: float


@dataclass(frozen=True)
class SignalRow:
    ticker: str
    date: date
    momentum: float
    volume_spike: float
    technical: float = 0.0
    fundamental: float = 0.0
    quality: float = 0.0
    short_momentum: float = 0.0
    medium_momentum: float = 0.0
    ma_trend: float = 0.0
    liquidity: float = 0.0


@dataclass(frozen=True)
class PickRow:
    date: date
    ticker: str
    score: float
    momentum: float
    volume: float
    risk: str
    technical: float = 0.0
    fundamental: float = 0.0
    quality: float = 0.0
    ma_trend: float = 0.0
    liquidity: float = 0.0
    horizon: str = "intraday"


@dataclass(frozen=True)
class Weights:
    date: date
    momentum_weight: float
    volume_weight: float


@dataclass(frozen=True)
class MarketSnapshot:
    date: date
    ticker: str
    company_name: str
    last_price: float
    high_price: float
    low_price: float
    daily_change_pct: float
    volume: float
    weekly_perf_pct: float
    monthly_perf_pct: float
    ytd_perf_pct: float
    yearly_perf_pct: float
    technical_hourly: str
    technical_daily: str
    technical_weekly: str
    technical_monthly: str
    avg_volume_3m: float
    market_cap: float
    beta: float
    revenue: float = 0.0
    pe_ratio: float = 0.0
