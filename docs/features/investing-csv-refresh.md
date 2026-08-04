# Investing.com CSV Refresh

## Command

```powershell
D:\miniconda3\python.exe -m stock_expert refresh-investing-csvs
```

Prefer Codex's embedded browser for operator-visible refreshes. On the page, select `Türkiye tüm hisse senetleri`, then expand `Daha Fazla` on the first table until the control disappears. Switching to Performans, Teknik, and Temel preserves the expanded row set, so do not repeat the clicks unless the control reappears.

The operator workflow uses Codex's embedded browser only. Standalone Edge and
Chrome launches are deliberately unsupported for this workflow because they
have repeatedly failed to produce reliable table data.

Visible mode is the default because it lets the user complete a site access challenge when one appears. `--headless` is available for environments where the page does not challenge automated sessions. The command does not bypass CAPTCHAs or Cloudflare controls.

Use the automation only with the permissions required by the data provider's terms.

## Publication Gates

- Every table must contain at least 500 rows by default.
- `Daha Fazla` is state-driven and limited to 12 clicks per tab.
- Source headers must match the existing four CSV schemas.
- All four tables must have identical company-name coverage, including duplicates.
- Files are quoted UTF-8 CSVs with a BOM.
- Existing live CSVs are replaced only after the complete bundle validates; failures restore the prior files.

The persistent browser profile is local and ignored at `data/.investing-browser-profile/`. The refresh command only updates CSV files; importing or running the persisted routine remains a separate operator action.

## Codex Plugin

`/stock-expert:refresh-data` runs the same validated refresh command, verifies
the published bundle, and opens `http://127.0.0.1:5173/?view=runs` unless the
user requests CLI-only output. The skill never confirms or starts the persisted
routine; Data & Runs remains the explicit execution boundary.

## Verification

On 2026-07-23, live extraction produced 646 rows in each file. Fiyat required six `Daha Fazla` clicks; the other tabs retained the expanded coverage. On 2026-07-25, the embedded-browser page reached 646 rows and no longer displayed the control after the same first-tab expansion. The generated bundle imported with zero malformed rows into an isolated test database.

The CLI launcher cannot attach directly to an already-open embedded-browser tab,
so the plugin workflow must capture from the embedded browser and then pass the
result through the same publication gates. Never publish a partial table or
silently fold refresh into `routine`.
