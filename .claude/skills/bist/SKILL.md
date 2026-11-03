---
name: bist
description: Refresh Stock Expert's four Investing.com BIST CSVs in the Claude desktop app's built-in browser, publish a validated bundle, then run the persisted routine. Use when the user says /bist, bist plugin, refresh then routine, or asks to update BIST data and run the routine without the web app.
---

# BIST Refresh Then Routine

Refresh the four live Investing.com CSVs in the built-in browser pane, publish only a validated bundle, then run the persisted routine. Do not start the web app.

## Preflight

1. Confirm the working directory is the repository root (it contains
   `stock_expert/` and `AGENTS.md`).
2. Read `memory.md`, `docs/tasks/current.md`, `docs/context/project.md`, and
   `docs/rules/output.md` in that order.
3. Record `git status --short` and the current branch, and preserve unrelated
   worktree changes. If the branch is not `main`, say so: `routine` then writes
   to that branch's database, not `data/stock_expert.db`.

## Refresh

Use only the built-in browser (`mcp__Claude_Browser__*`). Do not launch or fall
back to standalone Chrome or Edge, and do not use Claude in Chrome. Do not run
`python.exe -m stock_expert refresh-investing-csvs` or
`scripts/investing_csv_extract.mjs`. That launcher is not an embedded-browser
adapter.

1. Open `https://tr.investing.com/equities/turkey` with `preview_start`, then
   call `resize_window` with width 1440 and height 1000 and reload. The pane's
   default width serves a mobile layout without the Fiyat, Performans, Teknik,
   and Temel tabs. Confirm those four tabs are visible. The app clears the size
   when a turn ends or the pane's width changes, so set it again if they vanish.
2. If Cloudflare, CAPTCHA, or another access challenge is waiting on the user,
   stop and ask them to complete it in the browser pane. Do not bypass it.
3. Close the sign-up popup if it covers the page, using its X. Never sign in or
   create an account.
4. The market dropdown defaults to `BİST 100`. Open it with a real click and
   select `Türkiye tüm hisse senetleri`. Take a screenshot first to find it.
5. Expand the table by running this with `javascript_tool`. It clicks the
   footer control whose visible text is exactly `Daha Fazla`, not navigation
   items containing those words, and stops after 12 clicks:

```js
const norm=e=>(e.innerText||e.textContent||'').replace(/\s+/g,' ').trim();
const vis=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const table=()=>[...document.querySelectorAll('table')].sort((a,b)=>b.querySelectorAll('tbody tr').length-a.querySelectorAll('tbody tr').length)[0];
const footer=()=>[...document.querySelectorAll('button,[role=button],div,span,a')].filter(e=>vis(e)&&norm(e)==='Daha Fazla'&&!e.closest('nav,header')&&getComputedStyle(e).cursor==='pointer').pop();
await sleep(2500);
const log=[table().querySelectorAll('tbody tr').length];let clicks=0;
while(footer()&&clicks<12){const f=footer();f.scrollIntoView({block:'center'});const before=table().querySelectorAll('tbody tr').length;f.click();clicks++;for(let i=0;i<40&&table().querySelectorAll('tbody tr').length<=before;i++)await sleep(250);log.push(table().querySelectorAll('tbody tr').length);}
({clicks,log,footerLeft:!!footer()})
```

   Stop as a failure if `footerLeft` is true or the last `log` value is below
   500. Switching tabs keeps the expanded rows, so do not expand again unless
   the footer control reappears.
6. Capture all four tabs in one `javascript_tool` call. Empty-header columns,
   such as the row checkbox, are dropped:

```js
const norm=e=>(e.innerText||e.textContent||'').replace(/\s+/g,' ').trim();
const vis=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const table=()=>[...document.querySelectorAll('table')].sort((a,b)=>b.querySelectorAll('tbody tr').length-a.querySelectorAll('tbody tr').length)[0];
const expected={Fiyat:['fiyat.csv','Son'],Performans:['performans.csv','Günlük'],Teknik:['teknik.csv','Saatlik'],Temel:['temel.csv','Beta']};
const tables={};
for(const [tab,[file,marker]] of Object.entries(expected)){
  const btn=[...document.querySelectorAll('button')].filter(e=>vis(e)&&norm(e)===tab)[0];
  if(!btn) throw new Error('No tab button '+tab);
  btn.click();
  const headersNow=()=>[...table().querySelectorAll('thead th')].map(norm);
  for(let i=0;i<60&&!headersNow().includes(marker);i++)await sleep(250);
  if(!headersNow().includes(marker)) throw new Error('Headers did not load for '+tab+': '+headersNow());
  await sleep(500);
  const all=headersNow();
  const keep=all.map((h,i)=>h?i:-1).filter(i=>i>=0);
  const rows=[...table().querySelectorAll('tbody tr')].map(r=>{const c=[...r.children].map(norm);return keep.map(i=>c[i]??'')});
  tables[file]={headers:keep.map(i=>all[i]),rows};
}
JSON.stringify({tables})
```

   The result is too large to return inline. The tool reports an error that
   says "Output has been saved to" a path under `tool-results`. That is the
   expected outcome, not a failure. Do not read the file into the conversation
   and do not retype its rows.
7. Validate, then publish once, passing that path. The helper loads the capture
   and calls `stock_expert.investing_csv.publish_extracted_tables` into `data/`
   at `min_rows=500`. Do not publish a partial bundle and do not write the CSV
   files by hand.

```powershell
python.exe .claude\skills\bist\publish_capture.py "<saved path>" --dry-run
python.exe .claude\skills\bist\publish_capture.py "<saved path>"
```

8. Success requires matching company coverage, expected schemas, each file
   non-empty and starting with the UTF-8 BOM, and each file at least the minimum
   row count. The helper exits non-zero if any of these fail. Record
   `git status --short` after publication, then call `resize_window` with preset
   `desktop`.
9. If any refresh or publication check fails, stop. Do not run `routine`.

## Routine

Run this section only after a clean publication.

1. Run:

```powershell
python.exe -m stock_expert routine
```

2. Verify the printed `snapshot_id`, `review_run_id`, and related
   `review_pick_results` rows in the active SQLite database. `main` uses
   `data/stock_expert.db`. Other branches use `data/stock_expert_<branch>.db`
   unless `STOCK_EXPERT_DB_PATH` overrides it.
3. Run `git status --short`.
4. Report the pick basket, review result, snapshot/review ids, signal and
   target/review dates, SQLite verification, publication row counts, and git
   status.
5. Do not start `frontend/scripts/dev.mjs` or open `http://127.0.0.1:5173`.
