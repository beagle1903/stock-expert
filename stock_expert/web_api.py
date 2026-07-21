from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from stock_expert.config import Settings, get_settings
from stock_expert.constants import MIN_DAILY_WIN_RETURN
from stock_expert.database import connect, get_latest_snapshot_id, get_review_run, init_db
from stock_expert.services import market_context_for_dates
from stock_expert.trading_calendar import is_trading_session, next_trading_session, previous_trading_session


REQUIRED_CSV_FILES = ("fiyat.csv", "performans.csv", "teknik.csv", "temel.csv")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_REQUEST_BYTES = 64 * 1024
_ROUTINE_LOCK = threading.Lock()


class RoutineRequestError(Exception):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


def load_latest_review(settings: Settings) -> dict[str, Any] | None:
    init_db(settings)
    with connect(settings) as connection:
        review = connection.execute(
            """
            SELECT id, as_of_date, review_date, avg_return, win_rate, pick_count, wins
            FROM review_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        if review is None:
            return None
        outcomes = connection.execute(
            """
            SELECT ticker, return_pct, won
            FROM review_pick_results
            WHERE review_run_id = ?
            ORDER BY score DESC, ticker
            """,
            (review["id"],),
        ).fetchall()
    return {
        "id": int(review["id"]),
        "signalDate": str(review["as_of_date"]),
        "reviewDate": str(review["review_date"]),
        "averageReturn": float(review["avg_return"]),
        "winRate": float(review["win_rate"]),
        "wins": int(review["wins"]),
        "pickCount": int(review["pick_count"]),
        "minimumWinReturn": MIN_DAILY_WIN_RETURN,
        "outcomes": [
            {
                "ticker": str(outcome["ticker"]),
                "returnPct": float(outcome["return_pct"]),
                "won": bool(outcome["won"]),
            }
            for outcome in outcomes
        ],
    }


def _resolve_data_dir(settings: Settings, data_dir: str | Path) -> Path:
    path = Path(data_dir).expanduser()
    return path if path.is_absolute() else settings.base_dir / path


def _iso_local_timestamp(path: Path) -> tuple[str | None, date | None]:
    if not path.exists():
        return None, None
    modified = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    return modified.isoformat(timespec="minutes"), modified.date()


def build_routine_preview(
    settings: Settings,
    requested_signal_date: str,
    *,
    data_dir: str | Path = "data",
    today: date | None = None,
) -> dict[str, Any]:
    requested = date.fromisoformat(requested_signal_date)
    current_day = today or date.today()
    requested_is_session = is_trading_session(requested)
    resolved = requested if requested_is_session else previous_trading_session(requested)
    target = next_trading_session(resolved)
    resolved_data_dir = _resolve_data_dir(settings, data_dir)

    blocking_issues: list[str] = []
    warnings: list[str] = []
    if requested > current_day:
        blocking_issues.append("Future signal dates cannot be run.")
    if not requested_is_session:
        warnings.append(
            f"{requested.isoformat()} is not an open trading session; the signal date resolves to {resolved.isoformat()}."
        )
    if requested < current_day:
        warnings.append("This is a historical or missed-day run. Confirm that the live CSV files match the resolved signal date.")

    files: list[dict[str, Any]] = []
    newer_files: list[str] = []
    for name in REQUIRED_CSV_FILES:
        path = resolved_data_dir / name
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        modified_at, modified_date = _iso_local_timestamp(path)
        if not exists:
            status = "missing"
            blocking_issues.append(f"Missing required input: {name}.")
        elif size == 0:
            status = "empty"
            blocking_issues.append(f"Required input is empty: {name}.")
        elif modified_date is not None and modified_date < resolved:
            status = "stale"
            blocking_issues.append(
                f"{name} was last modified on {modified_date.isoformat()}, before the resolved signal date."
            )
        else:
            status = "ready"
            if modified_date is not None and modified_date > resolved:
                newer_files.append(name)
        files.append(
            {
                "name": name,
                "exists": exists,
                "sizeBytes": size,
                "modifiedAt": modified_at,
                "status": status,
            }
        )

    if newer_files:
        warnings.append(
            "Some filesystem timestamps are newer than the signal date. Timestamps do not prove the market date inside the files."
        )
    warnings.append("File presence and timestamps cannot verify the market date contained in the CSV rows.")

    token_payload = {
        "requested": requested.isoformat(),
        "resolved": resolved.isoformat(),
        "files": [(item["name"], item["status"], item["sizeBytes"], item["modifiedAt"]) for item in files],
    }
    confirmation_token = hashlib.sha256(
        json.dumps(token_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]

    return {
        "requestedSignalDate": requested.isoformat(),
        "resolvedSignalDate": resolved.isoformat(),
        "targetTradeDate": target.isoformat(),
        "requestedWasTradingSession": requested_is_session,
        "marketContext": market_context_for_dates(resolved, target),
        "calendarSource": "repository_confirmed",
        "files": files,
        "ready": not blocking_issues,
        "blockingIssues": blocking_issues,
        "warnings": warnings,
        "confirmationToken": confirmation_token,
    }


def _tail(value: str, limit: int = 6000) -> str:
    return value[-limit:]


def execute_routine(
    settings: Settings,
    requested_signal_date: str,
    confirmation_token: str,
    confirmed: bool,
    *,
    data_dir: str | Path = "data",
    today: date | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    preview = build_routine_preview(
        settings,
        requested_signal_date,
        data_dir=data_dir,
        today=today,
    )
    if not confirmed:
        raise RoutineRequestError("The resolved dates and CSV inputs must be confirmed before running.")
    if not preview["ready"]:
        raise RoutineRequestError("Routine inputs are not ready.", HTTPStatus.CONFLICT)
    if confirmation_token != preview["confirmationToken"]:
        raise RoutineRequestError("The preview is stale. Review the dates and files again.", HTTPStatus.CONFLICT)
    if not _ROUTINE_LOCK.acquire(blocking=False):
        raise RoutineRequestError("Another routine is already running.", HTTPStatus.CONFLICT)

    resolved_signal_date = preview["resolvedSignalDate"]
    command = [
        sys.executable,
        "-m",
        "stock_expert",
        "routine",
        "--date",
        resolved_signal_date,
        "--data-dir",
        str(data_dir),
    ]
    environment = os.environ.copy()
    environment.setdefault("PYTHONUTF8", "1")
    try:
        try:
            completed = runner(
                command,
                cwd=settings.base_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
                env=environment,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RoutineRequestError("The routine exceeded the 10-minute safety timeout.", HTTPStatus.GATEWAY_TIMEOUT) from exc
        except OSError as exc:
            raise RoutineRequestError("The routine process could not be started.", HTTPStatus.INTERNAL_SERVER_ERROR) from exc
        if completed.returncode != 0:
            detail = _tail(completed.stderr or completed.stdout or "Routine failed without output.")
            raise RoutineRequestError(detail, HTTPStatus.INTERNAL_SERVER_ERROR)

        resolved_date = date.fromisoformat(resolved_signal_date)
        init_db(settings)
        snapshot_id = get_latest_snapshot_id(settings, resolved_date)
        pick_count = 0
        if snapshot_id is not None:
            with connect(settings) as connection:
                pick_count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM picks WHERE snapshot_id = ?",
                        (snapshot_id,),
                    ).fetchone()[0]
                )
        review_signal_date = previous_trading_session(resolved_date)
        review = get_review_run(settings, review_signal_date, resolved_date)
        return {
            "ok": True,
            "requestedSignalDate": preview["requestedSignalDate"],
            "signalDate": resolved_signal_date,
            "targetTradeDate": preview["targetTradeDate"],
            "snapshotId": snapshot_id,
            "pickCount": pick_count,
            "reviewRunId": int(review["id"]) if review else None,
            "reviewSignalDate": review_signal_date.isoformat(),
            "reviewDate": resolved_signal_date,
            "completedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "outputTail": _tail(completed.stdout),
        }
    finally:
        _ROUTINE_LOCK.release()


class RoutineApiHandler(BaseHTTPRequestHandler):
    server: "RoutineApiServer"

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise RoutineRequestError("Invalid Content-Length header.") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise RoutineRequestError("Request body is missing or too large.")
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise RoutineRequestError("Request body must be valid JSON.") from exc
        if not isinstance(payload, dict):
            raise RoutineRequestError("Request body must be a JSON object.")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/health":
                self._send_json(HTTPStatus.OK, {"ok": True})
                return
            if parsed.path == "/api/reviews/latest":
                self._send_json(HTTPStatus.OK, {"review": load_latest_review(self.server.settings)})
                return
            if parsed.path == "/api/routine/preview":
                params = parse_qs(parsed.query)
                requested = params.get("signal_date", [date.today().isoformat()])[0]
                preview = build_routine_preview(
                    self.server.settings,
                    requested,
                    data_dir=self.server.data_dir,
                )
                self._send_json(HTTPStatus.OK, preview)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "signal_date must use YYYY-MM-DD format."})
        except RoutineRequestError as exc:
            self._send_json(exc.status, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover - last-resort HTTP boundary
            print(f"[web-api] unexpected preview error: {exc}", file=sys.stderr)
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Routine preview failed unexpectedly."})

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/routine":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return
        try:
            payload = self._read_json()
            result = execute_routine(
                self.server.settings,
                str(payload.get("requestedSignalDate", "")),
                str(payload.get("confirmationToken", "")),
                payload.get("confirmed") is True,
                data_dir=self.server.data_dir,
            )
            self._send_json(HTTPStatus.OK, result)
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "requestedSignalDate must use YYYY-MM-DD format."})
        except RoutineRequestError as exc:
            self._send_json(exc.status, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover - last-resort HTTP boundary
            print(f"[web-api] unexpected routine error: {exc}", file=sys.stderr)
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Routine failed unexpectedly. Check the local API log."})

    def log_message(self, format: str, *args: object) -> None:
        print(f"[web-api] {self.address_string()} {format % args}")


class RoutineApiServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        settings: Settings,
        data_dir: str | Path,
    ) -> None:
        super().__init__(server_address, RoutineApiHandler)
        self.settings = settings
        self.data_dir = data_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Stock Expert routine API")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--data-dir", default=os.environ.get("STOCK_EXPERT_WEB_DATA_DIR", "data"))
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("The routine API only binds to a loopback host.")
    server = RoutineApiServer((args.host, args.port), get_settings(), args.data_dir)
    print(f"Stock Expert routine API listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
