---
name: refresh-data
description: Refresh and validate Stock Expert's four live Investing.com BIST CSV inputs on the local desktop or in Codex Cloud, then hand off to the guarded Data & Runs web UI when that local UI exists. Use when the user says refresh data, fetch recent BIST data, update the Investing.com CSVs, prepare data for the routine, or asks for refresh-investing-csvs.
---

# Refresh BIST Data

Refresh the live CSV bundle without importing it or running the routine.

## Preflight

1. Confirm the repository root and read `memory.md`,
   `docs/tasks/current.md`, `docs/context/project.md`, and
   `docs/rules/output.md` in that order.
2. Preserve unrelated worktree changes and record `git status --short`.
3. Identify the execution surface:
   - On the local desktop, use Codex's embedded browser for Investing.com.
   - In Codex Cloud, use the headless repository extractor only when Node.js,
     a compatible Edge/Chrome/Chromium executable, and permitted network access
     are available.
   - If Cloud has no usable browser or the site presents an access challenge,
     ask for the four CSV files in one uploaded directory and use the upload
     command below. Never bypass CAPTCHA or Cloudflare.

## Capture

For the local desktop, use the embedded-browser skill to open
`https://tr.investing.com/equities/turkey`, confirm the Turkish
Fiyat/Performans/Teknik/Temel labels, select all Türkiye shares, expand the
rendered tables fully, and capture all four tabs.

For Cloud/headless capture, run from the repository root:

```bash
python3 -m stock_expert refresh-investing-csvs --headless
```

Do not use this standalone extractor as a local substitute for the embedded
browser. It cannot attach to an already-open embedded-browser tab.

For uploaded files, require the four expected files in one directory:

```bash
python3 -m stock_expert publish-investing-csvs --source-dir /path/to/csvs
```

This validates and publishes atomically; it does not import the snapshot or
run `routine`.

## Verify

Require all of the following before reporting success:

- `fiyat.csv`, `performans.csv`, `teknik.csv`, and `temel.csv` meet the minimum
  row count.
- Schemas and company coverage match across all four files.
- Each published file is non-empty and starts with the UTF-8 BOM.
- `git status --short` is recorded after publication.

## Handoff

On the local desktop, unless CLI-only output was requested, read
`../run/SKILL.md`, follow its start-or-reuse procedure, and open:

```text
http://127.0.0.1:5173/?view=runs
```

In Cloud, do not assume that local loopback URL is useful. Report the CLI
result and leave persisted execution to an explicit `routine` command.
