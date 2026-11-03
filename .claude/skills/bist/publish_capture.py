"""Validate or publish a /bist capture saved by the built-in browser's javascript_tool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from stock_expert.investing_csv import (  # noqa: E402
    CSV_HEADERS,
    InvestingCsvError,
    publish_extracted_tables,
    validate_extracted_tables,
)

MIN_ROWS = 500
UTF8_BOM = b"\xef\xbb\xbf"


def load_capture(path: Path) -> dict[str, Any]:
    # The saved file is a [{type, text}] array. The first text holds the JSON.stringify
    # result as a JSON string, followed by a "(captured at origin ...)" note.
    items = json.loads(path.read_text(encoding="utf-8"))
    payload = json.JSONDecoder().raw_decode(items[0]["text"])[0]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise InvestingCsvError("Capture does not contain a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="Path to the saved javascript_tool result")
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not touch data/")
    args = parser.parse_args()

    try:
        payload = load_capture(args.capture)
        if args.dry_run:
            print(f"valid: {validate_extracted_tables(payload, min_rows=MIN_ROWS)}")
            return 0

        destination = REPO_ROOT / "data"
        print(f"published: {publish_extracted_tables(payload, destination=destination, min_rows=MIN_ROWS)}")
        for filename in CSV_HEADERS:
            if not (destination / filename).read_bytes().startswith(UTF8_BOM):
                raise InvestingCsvError(f"{filename} does not start with the UTF-8 BOM")
    except (InvestingCsvError, OSError, ValueError, LookupError) as error:
        print(f"failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
