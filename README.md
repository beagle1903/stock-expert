# Stock Expert

Python CLI for BIST intraday idea generation and review.

Current runtime mode: daily CSV snapshots.

## Start Here

- Current task: [docs/tasks/current.md](/C:/Users/burha/Documents/stock%20expert/docs/tasks/current.md)
- Project context: [docs/context/project.md](/C:/Users/burha/Documents/stock%20expert/docs/context/project.md)
- Output rules: [docs/rules/output.md](/C:/Users/burha/Documents/stock%20expert/docs/rules/output.md)
- Architecture: [docs/context/architecture.md](/C:/Users/burha/Documents/stock%20expert/docs/context/architecture.md)
- Decisions: [docs/context/decisions.md](/C:/Users/burha/Documents/stock%20expert/docs/context/decisions.md)

## Commands

```bash
python -m stock_expert import-daily-csv --date 2026-04-05
python -m stock_expert daily
python -m stock_expert picks
python -m stock_expert review
```

## Data

- SQLite: `data/stock_expert.db`
- Daily CSV inputs: `fiyat.csv`, `performans.csv`, `teknik.csv`, `temel.csv`
- Optional ticker override map: `data/ticker_map.csv`

## Notes

- Feature docs live in [docs/features](/C:/Users/burha/Documents/stock%20expert/docs/features)
- Scratch files live in [docs/scratch](/C:/Users/burha/Documents/stock%20expert/docs/scratch) and should not be edited during normal task work
- Root guidance lives in [AGENTS.md](/C:/Users/burha/Documents/stock%20expert/AGENTS.md)
