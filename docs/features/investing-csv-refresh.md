# Investing.com CSV Refresh

## Command

```powershell
D:\miniconda3\python.exe -m stock_expert refresh-investing-csvs
```

On the local desktop, prefer Codex's embedded browser for operator-visible
refreshes. Open `https://tr.investing.com/equities/turkey`, confirm the Turkish
Fiyat/Performans/Teknik/Temel labels, select `Türkiye tüm hisse senetleri`, then
expand `Daha Fazla` on the first table until the control disappears. Switching
tabs preserves the expanded row set, so do not repeat the clicks unless the
control reappears.

The local operator workflow uses Codex's embedded browser. The repository CLI
extractor is a separate adapter for Cloud/headless environments and is only
usable when a compatible browser and permitted network access are available.
If Cloud cannot start a browser or receives an access challenge, supply the
four CSV files and use the upload command below.

Visible mode is the default because it lets the user complete a site access challenge when one appears. `--headless` is available for environments where the page does not challenge automated sessions. The command does not bypass CAPTCHAs or Cloudflare controls.

Use the automation only with the permissions required by the data provider's terms.

## Publication Gates

- Every table must contain at least 500 rows by default.
- `Daha Fazla` is state-driven and limited to 12 clicks per tab.
- Source headers must match the existing four CSV schemas.
- All four tables must have identical company-name coverage, including duplicates.
- Files are quoted UTF-8 CSVs with a BOM.
- Existing live CSVs are replaced only after the complete bundle validates; failures restore the prior files.
- The subsequent daily import detects numeric locale and rejects live-size bundles whose resolved ticker coverage falls below 75%, preventing a translated company-name set from becoming a partial operational snapshot.

The persistent browser profile is local and ignored at `data/.investing-browser-profile/`. The refresh command only updates CSV files; importing or running the persisted routine remains a separate operator action.

## Uploaded CSV fallback

Place `fiyat.csv`, `performans.csv`, `teknik.csv`, and `temel.csv` in one
directory, then run:

```bash
python3 -m stock_expert publish-investing-csvs --source-dir /path/to/csvs
```

The command applies the same schema, minimum-row, company-coverage, quoted
UTF-8-with-BOM, and rollback-safe publication gates as browser capture. It
does not import the snapshot or run the routine.

For SQLite history plus the current CSV bundle, use the portable workflow in
[Cloud-first operation](cloud-operation.md).

## Codex Plugin

`/stock-expert:refresh-data` selects the capture surface: embedded browser on
the local desktop, headless extraction in Cloud when available, or validated
uploaded CSV publication as the fallback. A successful local refresh opens
`http://127.0.0.1:5173/?view=runs`; Cloud reports the CLI result because it does
not assume a local loopback handoff. The skill never confirms or starts the
persisted routine.

## Verification

On 2026-07-23, live extraction produced 646 rows in each file. Fiyat required six `Daha Fazla` clicks; the other tabs retained the expanded coverage. On 2026-07-25, the embedded-browser page reached 646 rows and no longer displayed the control after the same first-tab expansion. The generated bundle imported with zero malformed rows into an isolated test database.

The CLI launcher cannot attach directly to an already-open embedded-browser tab,
so the plugin workflow must capture from the embedded browser and then pass the
result through the same publication gates. Never publish a partial table or
silently fold refresh into `routine`.
