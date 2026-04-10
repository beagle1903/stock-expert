# 📈 CLI BIST Intraday Stock Advisor (v1 Spec)

## 🧠 Overview

This system is a **CLI-based stock advisor for BIST** focused on **intraday trading**:

* Buy: market open
* Sell: same-day close
* Data: end-of-day (EOD)
* Output: structured signals (no natural language)
* Picks: 5–10 stocks daily

---

## 🎯 Core Idea

The system generates **daily stock picks** based on:

1. KAP disclosures (primary signal)
2. Price momentum
3. Volume spikes

Then evaluates itself weekly using:

* performance analysis
* missed opportunities
* automatic weight adjustment

---

## 🧱 CLI Commands

### 1. Daily Market Summary

```bash
stocks daily
```

Output:

* BIST100 summary
* key movers
* KAP highlights (last 2–3 days)

---

### 2. Daily Picks

```bash
stocks picks
```

Output (structured):

```json
{
  "ticker": "ASELS",
  "score": 0.82,
  "signals": {
    "kap": 0.9,
    "momentum": 0.7,
    "volume": 0.6
  },
  "risk": "medium",
  "horizon": "intraday"
}
```

---

### 3. Weekly Review

```bash
stocks review
```

Always evaluates **last 7 days**

Output:

```json
{
  "performance": {
    "avg_return": 0.018,
    "win_rate": 0.6
  },
  "missed": [
    {
      "ticker": "THYAO",
      "return": 0.06,
      "reason": "kap_weight_too_low"
    }
  ],
  "adjustments": {
    "kap_weight": 0.55,
    "momentum_weight": 0.27,
    "volume_weight": 0.18
  }
}
```

---

## 📊 Market Context

* Borsa Istanbul is the main exchange in Türkiye
* The **BIST100 index** represents the top 100 companies and is the main benchmark

---

## 🧠 KAP (Critical Signal)

* Public Disclosure Platform is the official disclosure system
* All listed companies must publish important information here ([Kap][1])
* Includes:

  * financial results
  * contracts
  * investments
  * material events

👉 KAP disclosures can directly impact stock prices ([Borsa Atlas][2])

---

## 🧠 Signals

### 1. Momentum

```python
momentum = (close_today - close_3_days_ago) / close_3_days_ago
```

---

### 2. Volume Spike

```python
volume_spike = volume_today / avg_volume_last_5_days
```

---

### 3. KAP Signal

Keyword-based scoring:

Positive keywords:

* contract
* agreement
* profit
* investment

Negative keywords:

* loss
* lawsuit
* debt

Normalize score to range [0, 1]

---

## ⚖️ Scoring Formula

```python
score =
  kap_weight * kap_signal +
  momentum_weight * momentum +
  volume_weight * volume_spike
```

### Initial weights

```python
kap_weight = 0.5
momentum_weight = 0.3
volume_weight = 0.2
```

---

## 🚫 Risk Filtering

Exclude stocks with:

* low liquidity
* extreme volatility

---

## 🗃️ Database (SQLite)

### stocks

```sql
ticker TEXT
date DATE
close_price REAL
volume REAL
```

---

### signals

```sql
ticker TEXT
date DATE
kap_score REAL
momentum REAL
volume_spike REAL
```

---

### picks

```sql
date DATE
ticker TEXT
score REAL
kap REAL
momentum REAL
volume REAL
```

---

### weights

```sql
date DATE
kap_weight REAL
momentum_weight REAL
volume_weight REAL
```

---

## 🔁 Daily Pipeline

1. Fetch EOD price + volume data
2. Fetch KAP (last 2–3 days)
3. Compute signals
4. Apply scoring
5. Filter + rank
6. Store picks

---

## 🔁 Weekly Review Logic

### Step 1: Evaluate Picks

* calculate returns (open → close)
* compute win rate

---

### Step 2: Find Missed Stocks

* identify top movers of the week
* compare against picks

---

### Step 3: Adjust Weights

Example:

```python
kap_weight += 0.05
momentum_weight -= 0.03
```

---

## ⚠️ Critical Constraints

* NO future data leakage
* Only use data available at decision time
* KAP must be filtered (not all disclosures matter)

---

## 🚀 MVP Scope

### Included

* CLI commands
* SQLite database
* batch processing
* rule-based signals
* automatic weight adjustment

---

### Excluded

* UI / dashboard
* real-time trading
* complex ML models

---

## 🧠 System Identity

This is NOT just a stock picker.

It is:

> A self-improving intraday stock selection system for BIST

---

## 🏁 End

This document is the **single source of truth** for v1 implementation.

[1]: https://kap.org.tr/en/about/general-information?utm_source=chatgpt.com "public disclosure platform (kap) - PDP"
[2]: https://borsaatlas.com/akademi/kap-nedir-finansal-raporlar-platformu/?utm_source=chatgpt.com "KAP Nedir: Yatırımcıların 2025 için Bilgi Merkezi - Borsa Atlas"
