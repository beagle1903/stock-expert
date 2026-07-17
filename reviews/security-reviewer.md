# Security Review

Scope: full tracked application, tests, configuration, hook/plugin definitions, and recent commits `9ff2846` / `6f2acca`. The application is a single-user local CLI, so findings that require the operator to supply a malicious local argument or file are rated P2. No P0 or P1 findings.

## P2 — `--output` can truncate any writable file

**Evidence:** `stock_expert/cli.py:55-57` describes a project-relative output but does not enforce it. `stock_expert/yahoo.py:140` joins the untrusted value without resolving/validating containment; an absolute path or `..` escapes the repository. `stock_expert/yahoo.py:119-121` creates parents and opens with `"w"`, truncating an existing target even when no market rows were downloaded.

**Impact:** A mistaken or wrapper-controlled argument can overwrite any file writable by the CLI user. Symlink/reparse-point targets are also followed.

**Suggested fix:** Resolve the destination, require it to remain beneath an approved output directory (normally `settings.data_dir`), reject symlinks/reparse points and non-`.csv` targets, and write atomically through a sibling temporary file. Add traversal, absolute-path, symlink, and existing-file tests.

## P2 — Local and remote ingestion has no resource bounds

**Evidence:** All four snapshots are fully materialized in memory (`stock_expert/daily_csv.py:96-103, 122-125`). XLSX processing decompresses and parses the full worksheet without checking archive/member size or compression ratio (`stock_expert/yahoo.py:101-106`). Yahoo responses are read without a byte cap (`stock_expert/yahoo.py:45-46`).

**Impact:** An oversized/malicious CSV, XLSX zip bomb, or unexpectedly large upstream response can exhaust memory/disk/CPU and terminate a routine before persistence completes. This is availability risk, not code execution.

**Suggested fix:** Define maximum file bytes, rows, columns, field length, worksheet uncompressed size/compression ratio, response bytes, and ticker count. Stream CSV rows where practical; reject limits before allocation and test oversized fixtures.

## P2 — Direct ticker input permits control characters and malformed identifiers

**Evidence:** `normalize_yahoo_symbol` only strips and uppercases (`stock_expert/yahoo.py:29-33`). The resulting value is printed directly (`stock_expert/yahoo.py:146-152`) and can reach CSV/SQLite after a successful response. In contrast, workbook tickers already receive an alphanumeric/length filter (`stock_expert/yahoo.py:110-112`).

**Impact:** Crafted CLI values can inject terminal control sequences, spoof progress/error output, create inconsistent identifiers, and complicate downstream CSV handling.

**Suggested fix:** Apply one canonical validator to every ticker source (for example an explicit BIST allowlist regex and length bound), reject control characters before logging, and test ANSI/newline, empty, overlong, Unicode-confusable, and suffix cases.

## P2 — Build dependency is open-ended and unverified

**Evidence:** `pyproject.toml:10-12` installs `setuptools>=68` in the isolated build environment; there is no lockfile or hash-pinned build bootstrap.

**Impact:** Builds are not reproducible and automatically trust any future compatible release fetched from the configured package index, increasing supply-chain exposure.

**Suggested fix:** Pin an audited setuptools version (or bounded compatible range), make release/CI installation use a hash-locked constraints file and trusted index, and add dependency scanning/update automation.

## No finding in major checked areas

- **Secrets:** no tracked credentials/private keys; `.env`, Codex local config, and SQLite databases are ignored. `.env.example` contains only a local DB path.
- **SQL injection/integrity:** externally derived values use SQLite parameters. Dynamic table names/placeholders are selected from fixed internal lists. Foreign keys are enabled; snapshot/review bundles use transactions and unique identities.
- **Command injection:** subprocess calls use fixed argument arrays with `shell=False`; no `eval`, unsafe deserialization, or shell interpolation found.
- **Network/SSRF:** Yahoo uses a fixed HTTPS host and percent-encodes the path symbol. No user-controlled scheme/host found.
- **Recent plugin changes:** the routine skill invokes the documented local command and introduces no secret handling or new executable interpolation. Its persisted write behavior is explicit in the skill description.
- **XML entity execution:** no external entity-capable parser/configuration found; the residual XLSX concern is resource exhaustion covered above.
