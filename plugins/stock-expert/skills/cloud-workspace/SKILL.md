---
name: cloud-workspace
description: Move Stock Expert's ignored CSV and SQLite runtime state between local and Codex Cloud workspaces using validated uploads and checksummed workspace bundles. Use when the user asks about Cloud workspace setup, CSV upload/download, local/Cloud continuity, or SSH/file transfer.
---

# Cloud Workspace Handoff

Use Codex Cloud for repository execution when possible. Do not require an SSH
session. The tracked repository is the code boundary; CSVs, SQLite state,
`.env`, and the Investing.com browser profile are runtime data.

## Import

If historical continuity is needed, locate the uploaded ZIP and run:

```bash
python3 -m stock_expert import-workspace-bundle \
  --input /path/to/stock_expert_workspace.zip \
  --replace-database
```

The command verifies the manifest, SHA-256 member checksums, SQLite integrity,
and CSV gates before replacement. An existing active database is backed up
under `data/backups/`.

If only current CSVs are supplied, locate a directory containing
`fiyat.csv`, `performans.csv`, `teknik.csv`, and `temel.csv`, then run:

```bash
python3 -m stock_expert publish-investing-csvs \
  --source-dir /path/to/csvs
```

## Capture and run

Try `python3 -m stock_expert refresh-investing-csvs --headless` only when Cloud
has a compatible browser and permitted network access. If the browser is
missing or the site challenges the session, use uploaded CSVs; never bypass an
access control. Run `routine` only as an explicit follow-up.

## Export

When local continuity is wanted after a Cloud run:

```bash
python3 -m stock_expert export-workspace-bundle \
  --output data/backups/stock_expert_workspace.zip
```

Leave the ZIP uncommitted and use the Cloud task's file/artifact download
surface to bring it back to the local workspace. The local embedded-browser
and loopback Data & Runs workflows remain local-desktop paths.

Do not run stateful routines against the same logical history concurrently in
local and Cloud. Export/import is the handoff point.
