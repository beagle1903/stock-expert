# Investing.com CSV Refresh

## Command

```powershell
D:\miniconda3\python.exe -m stock_expert refresh-investing-csvs
```

Prefer Cursor's embedded browser for operator-visible refreshes. Open `https://tr.investing.com/equities/turkey`, confirm the Turkish Fiyat/Performans/Teknik/Temel labels, select `Türkiye tüm hisse senetleri`, then expand the equity-table footer control whose visible text is exactly `Daha Fazla` (the cursor-pointer row under the table) until that control disappears. Do not click navigation items that merely contain the words Daha Fazla. Switching tabs preserves the expanded row set, so do not repeat the clicks unless the footer control reappears.

The `/bist` operator workflow uses Cursor's in-app browser only. Standalone Edge
and Chrome launches are deliberately unsupported for this workflow because they
have repeatedly failed to produce reliable table data. `refresh-investing-csvs`
is not that embedded-browser adapter.

Visible mode is the default because it lets the user complete a site access challenge when one appears. `--headless` is available for environments where the page does not challenge automated sessions. The command does not bypass CAPTCHAs or Cloudflare controls.

Use the automation only with the permissions required by the data provider's terms.

## Publication Gates

- Every table must contain at least 500 rows by default.
- The equity-table `Daha Fazla` control is the footer row under the table, not a navigation item. Expansion is state-driven and limited to 12 clicks. Stop if the footer is still present after 12 clicks or the table stalls below 500 rows.
- Source headers must match the existing four CSV schemas, or those schemas plus one optional recognized symbol/code column immediately before or after `İsim`. A Kod column is not required; current live tables without a symbol still validate and publish
- If an optional symbol column is present, publication keeps it so daily import can use it, and the bundle is rejected when the same company name maps to different valid symbols across tables
- All four tables must have identical company-name coverage, including duplicates.
- Files are quoted UTF-8 CSVs with a BOM.
- Existing live CSVs are replaced only after the complete bundle validates; failures restore the prior files.
- The subsequent daily import detects numeric locale and rejects live-size bundles whose resolved ticker coverage falls below 75%, preventing a translated company-name set from becoming a partial operational snapshot.

The persistent browser profile is local and ignored at `data/.investing-browser-profile/`. The refresh command only updates CSV files; importing or running the persisted routine remains a separate operator action.

## BIST Plugin

`/bist` (project skill `.cursor/skills/bist/SKILL.md`, packaged by
`plugins/bist/`) refreshes the four tables in Cursor's embedded browser and
publishes them with `publish_extracted_tables` at `min_rows=500`. It runs
`routine` only after that validated publish succeeds. It does not start the
web app or open Data & Runs. A failed refresh or publication stops before
`routine`. Do not use `refresh-investing-csvs` for this workflow.

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
