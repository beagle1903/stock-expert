---
name: refresh-data
description: Refresh and validate Stock Expert's four live Investing.com BIST CSV inputs in the Claude desktop app's built-in browser, then hand off to the guarded Data & Runs web UI without running the routine. Use when the user says /refresh-data, refresh data, fetch recent BIST data, update the Investing.com CSVs, prepare data for the routine, or asks for refresh-investing-csvs.
---

# Refresh BIST Data

Refresh the live CSV bundle without importing it or running the routine.

## Preflight

1. Confirm the working directory is the repository root (it contains
   `stock_expert/` and `AGENTS.md`).
2. Read `memory.md`, `docs/tasks/current.md`, `docs/context/project.md`, and
   `docs/rules/output.md` in that order.
3. Preserve unrelated worktree changes and record `git status --short`.
4. Use only the built-in browser (`mcp__Claude_Browser__*`) for every
   Investing.com interaction. Do not launch or fall back to standalone Chrome
   or Edge, and do not use Claude in Chrome.

## Refresh

Read `.claude/skills/bist/SKILL.md` and follow its **Refresh** section exactly,
steps 1 through 8: open `https://tr.investing.com/equities/turkey` at a
1440x1000 viewport, confirm the Turkish Fiyat/Performans/Teknik/Temel tabs,
select all Türkiye shares, expand the rendered table, capture all four tabs in
one call, then validate and publish the saved capture with
`.claude\skills\bist\publish_capture.py` (`--dry-run` first). That section is
the single source for the page scripts; do not copy or rewrite them here.

The repository CLI launcher (`python.exe -m stock_expert refresh-investing-csvs`
and `scripts/investing_csv_extract.mjs`) is not a built-in browser adapter and
must not be used for this workflow. Do not bypass CAPTCHA, Cloudflare, or
another access challenge. When a challenge appears, ask the user to complete it
in the browser pane.

Do not run `routine` automatically, and do not follow the **Routine** section
of the `bist` skill. Data refresh and persisted execution are separate operator
actions.

## Verify

Require all of the following before reporting success:

- `fiyat.csv`, `performans.csv`, `teknik.csv`, and `temel.csv` each meet the
  minimum row count reported by the publish helper.
- The helper confirms matching company coverage and expected schemas.
- Each published file is non-empty and starts with the UTF-8 BOM.
- `git status --short` is recorded after publication.

If any check fails, stop and report it. Do not hand off to the web UI with a
partial or unvalidated bundle.

## Web Handoff

Unless the user requested CLI-only output, read
`.claude/skills/console/SKILL.md`, follow its start-or-reuse procedure, and
open:

```text
http://127.0.0.1:5173/?view=runs
```

Leave the persisted routine for the user to review and confirm in Data & Runs.
Report the four row counts, publication result, UI/API health, and git status.
