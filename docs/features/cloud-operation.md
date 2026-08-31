# Cloud-first operation

Codex Cloud is the preferred execution surface for repository work. A Cloud
task starts from the selected Git revision, so ignored runtime artifacts are
not automatically carried over:

- `data/fiyat.csv`, `performans.csv`, `teknik.csv`, and `temel.csv`
- branch-specific `data/stock_expert*.db`
- `.env` and `data/.investing-browser-profile/`

The tracked `data/ticker_map.csv` remains part of the repository. The strategy
and persistence code do not change between local and Cloud workspaces.

## Move state into Cloud

For historical continuity, create a portable bundle in the source workspace:

```powershell
python -m stock_expert export-workspace-bundle --output data/backups/stock_expert_workspace.zip
```

Upload that ZIP to the Cloud task. After the file is available in the task,
restore it before a stateful run:

```bash
python3 -m stock_expert import-workspace-bundle \
  --input /path/to/stock_expert_workspace.zip \
  --replace-database
```

Import validates the manifest, member checksums, SQLite integrity, and all four
CSV schemas/coverage gates. If a database already exists, the explicit replace
flag is required and a backup is written under `data/backups/`.

If only fresh CSV inputs are needed, upload a directory containing all four
files and publish it instead:

```bash
python3 -m stock_expert publish-investing-csvs \
  --source-dir /path/to/uploaded-csvs
```

## Capture options

In Cloud, first try:

```bash
python3 -m stock_expert refresh-investing-csvs --headless
```

This requires Node.js, a compatible Edge/Chrome/Chromium executable, and
permitted network access. It does not bypass CAPTCHA or access challenges. If
the browser is unavailable or the site challenges the session, use the four-file
upload path. On the local desktop, use the embedded-browser refresh workflow;
the standalone extractor is not the local embedded-browser adapter.

## Move state back to local

After a Cloud routine, export a new bundle when local continuity is wanted:

```bash
python3 -m stock_expert export-workspace-bundle \
  --output data/backups/stock_expert_workspace.zip
```

Download that artifact from the Cloud task and import it into the chosen local
branch. There is no SSH step in this workflow. Do not run local and Cloud
stateful routines against the same logical history concurrently; each export
is a deliberate handoff point.

The loopback Data & Runs web app remains a local-desktop workflow for now. The
portable Cloud boundary is the validated CSV/SQLite CLI workflow.
