# Investing.com CSV Refresh

## Command

```powershell
D:\miniconda3\python.exe -m stock_expert refresh-investing-csvs
```

The command opens a dedicated visible Edge or Chrome profile, confirms the Türkiye stock page, selects `Türkiye tüm hisse senetleri`, and expands `Daha Fazla` until the control disappears. It then extracts the rendered Fiyat, Performans, Teknik, and Temel tables.

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

## Verification

On 2026-07-23, live extraction produced 646 rows in each file. Fiyat required six `Daha Fazla` clicks; the other tabs retained the expanded coverage. The generated bundle imported with zero malformed rows into an isolated test database.
