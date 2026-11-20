# Current Task

- Maintain a minimal working BIST CLI with:
  - `import-daily-csv`
  - `refresh-investing-csvs`
  - `routine`
  - `daily`
  - `picks`
  - `review`

## Constraints

- Keep outputs concise and structured
- Prefer simple solutions
- Avoid unrelated refactors
- Ask before adding dependencies or major architecture changes

## Done When

- Commands run end-to-end
- Review explains missed movers clearly
- Daily CSV import flow is available
- Live root CSV routine supports repeated same-day imports
- Rendered Investing.com tables can refresh all four live CSVs with cross-table coverage validation and rollback-safe publication
- Routine and `review --dry-run` behavior are covered by tests
- Snapshot and review persistence are atomic and idempotent
- Historical review evidence is point-in-time and immutable
- Standard-library trace coverage remains at or above 90% across production modules

## Bucketed-Default Pilot

- [x] Persist complete breadth-matched score-ranked and bucketed baskets
- [x] Use bucketed as the active default without changing candidate scoring
- [x] Freeze momentum/volume weights while the pilot is active
- [x] Count only complete paired review sessions
- [x] Roll back at a -3 percentage-point compounded edge
- [x] Decide promotion after 10 sessions using at least 6 wins and a +3-point edge
- [x] Apply terminal review decisions before persisting the next basket
- [x] Publish operational and paired pilot baskets atomically
- [x] Keep pre-start dates outside pilot evidence and evaluate sessions chronologically
- [x] Make reviewed baskets immutable and persist missing-price sessions as incomplete

## Frontend Prototype

- Dark Evidence Console implemented under `frontend/`. Every evidence panel reads live loopback APIs; the orphaned mock fixture is removed.
- Boot distinguishes loading, empty basket, and API error. Error copy is not the empty-basket message.
- Responsive browser and design QA are recorded in `frontend/design-qa.md`.
- Python strategy and SQLite behavior are unchanged.
- Data & Runs now has a loopback-only persisted routine launcher with holiday/missed-day routing, CSV readiness checks, confirmation, progress, and result IDs.
- The Claude Code `/console` skill starts or reuses the web app, waits for the watchdog, and opens it in the Claude desktop app's built-in browser pane.
- Claude Code project skills in `.claude/skills/` are the current operator path: `/routine`, `/console`, `/refresh-data`, and `/bist`. The Cursor and Codex overlays (`.cursor/`, `.codex/`, `plugins/`, `.agents/`) were removed on 2026-11-14 under GitHub issue #36 and exist only in git history.
- GitHub issue #32: the `/bist` skill refreshes the four Investing.com CSVs in the built-in browser pane, publishes a validated bundle, then runs `routine`, and does not start the web app.
- `.claude/skills/bist/` ports `/bist` to Claude Code using the desktop app's built-in browser pane. Capture and validation were exercised against the live site (662 rows per table), and the full skill (publish plus `routine`) was run end to end from Claude Code on 2026-11-14.
- GitHub issue #36 (remove `.cursor/` and `.codex/` after migrating to Claude Code), step 1: the docs validator now lives at `scripts/validate_docs_update.py`, Claude Code runs it as a Stop hook from `.claude/settings.json`, and the Cursor adapter and Codex hook call the new path. See `docs/context/docs-stop-hook.md`.
- GitHub issue #36, step 2: `.claude/skills/` now also holds `/routine`, `/refresh-data`, and `/console` (Cursor's `/run`, renamed to avoid Claude Code's built-in `run` skill), and `.claude/agents/` holds the four `se-*` subagents. `tests/test_project_skills.py` and the Claude Code cases in `tests/test_project_subagents.py` pin them. The three new skills have not been run end to end from Claude Code yet. Always-on rules, the remaining doc updates, and the folder deletion are later steps.
- GitHub issue #36, step 3: the three Cursor always-on rules (always open a PR, always dispatch project subagents, subagent roster/cascade/reporting) now live in `docs/rules/workflow.md` in Claude Code terms, and `CLAUDE.md` states both standing rules because it is the file Claude Code always loads. `ClaudeCodeStandingRulesTests` in `tests/test_project_subagents.py` pins them. The `.cursor/rules/*.mdc` copies stay until the folder deletion step.
- GitHub issue #36, step 4: the test suite no longer reads `.cursor/` or `.codex/`. `scripts/validate_docs_update.py` itself now falls back to the last assistant entry of `transcript_path` for the docs-not-needed marker (previously only the Cursor adapter did), `tests/test_docs_stop_hook.py` covers that with Claude Code Stop payloads, and `tests/test_project_subagents.py` pins the `.claude/agents/` instructions with phrase needles instead of comparing them to the Cursor copies. The folders themselves stay until the deletion step.
- GitHub issue #36, step 5: the documentation now describes Claude Code as the only operator path. The hook doc was renamed to `docs/context/docs-stop-hook.md`, `docs/context/codex-commands.md` and `docs/context/cursor-operator.md` carry a "Historical" banner, and the remaining Cursor and Codex descriptions sit under clearly labelled leftover or retired sections that step 6 deletes together with `.cursor/`, `.codex/`, `plugins/`, and `.agents/`. `docs/superpowers/*` and dated decision or change-log rows are left as written.
- GitHub issue #36, step 6: `.cursor/`, `.codex/`, `plugins/`, and `.agents/` are deleted, and `scripts/validate_docs_update.py` no longer gates `.codex/` or `.cursor/` paths or dead-code checks `.cursor/hooks/`. `tests/test_project_skills.py` asserts the four folders stay absent, and `tests/test_docs_stop_hook.py` asserts their paths are no longer gated. Issue #36's work is complete apart from operator-side checks: a live Stop hook block observed in a real Claude Code session, and running `/routine`, `/console`, and `/refresh-data` once end to end.
- Reviews load persisted history and selectable historical outcomes from SQLite and refresh after a successful routine; compact date navigation, older/newer controls, and a detail-first narrow layout keep the history usable.
- Data & Runs no longer includes the UI-only Presentation states preview controls.
- The Claude Code `/refresh-data` skill publishes a validated BIST CSV bundle and hands successful refreshes to the direct `?view=runs` web entry point without running the routine.
- The web-app launcher behind `/console` (`frontend/scripts/dev.mjs`) starts only missing UI/API components, retains component pids and ignored logs, and requires a launcher-owned five-minute post-boot watchdog result for both new and reused processes.

## Active Enhancement

- GitHub issue #45 (signal windows silently span missing sessions) is on
  `signal-window-gaps`. Each persisted publication records its
  signal-window coverage, and a gap is shown as degraded evidence in CLI
  output, the APIs, and the Evidence Console. Scores, exposure, and
  selection are unchanged, and older baskets read `not_captured`.

- GitHub issue #41 (complete the BIST trading calendar) shipped on `main`
  via [PR #60](https://github.com/beagle1903/stock-expert/pull/60) and is
  closed. Fixed national holidays are recurring closures,
  28 October is a recurring half day, 2026 variable dates come from Borsa
  İstanbul notice 41625, half days moved out of `services.py`, and an
  unconfirmed year warns in `routine` and the Data & Runs preview. 2027
  variable dates wait for the December 2026 announcement. See
  `docs/context/trading-calendar.md`. Ranking and stored evidence are
  unchanged. A review evidence guard makes persisted `review` and
  `routine` refuse, before any write or import, a run whose review date or
  signal basket already has a review under a different key.

- Live Evidence Console honesty (remove mock fixture, distinguish boot
  error vs empty basket, drop hardcoded ticker default) is on
  `live-evidence-panels` for GitHub issue #13. See
  `docs/tasks/live-evidence-panels.md`. Python ranking, review, import,
  and SQLite strategy stay unchanged.
- Import canonical source symbol/code, keep `ticker_map.csv` as fallback
  shipped on `main` via
  [PR #29](https://github.com/beagle1903/stock-expert/pull/29). GitHub issue
  #12 is closed. Ranking, picks, review, and latest-picks selection stay
  unchanged.
- Workflow docs for mandatory PRs and always-dispatch project subagents
  shipped on `main` via
  [PR #27](https://github.com/beagle1903/stock-expert/pull/27). GitHub issue
  #26 is closed. Canonical rule: `docs/rules/workflow.md`.
- Fade-then-rechase penalty and miss tags shipped on `main` via
  [PR #23](https://github.com/beagle1903/stock-expert/pull/23). GitHub issue
  #21 is closed. See `docs/tasks/fade-then-rechase.md`.
- Snapshots API (`/api/snapshots/history`, `/api/snapshots/{id}`) and the
  read-only Evidence Console Snapshots view shipped on `main` via
  [PR #19](https://github.com/beagle1903/stock-expert/pull/19). GitHub issue
  #11 is closed. Verification is in
  `docs/tasks/data-quality-snapshot-history.md`.
- Spec: `docs/superpowers/specs/2026-09-16-data-quality-snapshot-history-design.md`.
- Plan: `docs/superpowers/plans/2026-09-16-data-quality-snapshot-history.md`.
- Implementation notes: `docs/tasks/data-quality-snapshot-history.md`.
- Basic GitHub CI now gates pull requests and `main` with Python tests plus
  frontend tests and a production build; deployment is intentionally deferred.
- Optional Yahoo path and `midday-routine` removal shipped on `main` via
  [PR #25](https://github.com/beagle1903/stock-expert/pull/25). GitHub issue
  #14 is closed. See `docs/features/download-ohlcv.md`.
- Removed redundant `openwiki/` generated wiki; `docs/` is the source of truth.
