from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from stock_expert.config import Settings
from stock_expert.investing_csv import (
    CSV_HEADERS,
    load_csv_bundle,
    stage_extracted_tables,
    validate_csv_bundle,
)


BUNDLE_FORMAT = "stock_expert_workspace"
BUNDLE_VERSION = 1
DATABASE_MEMBER = "state/stock_expert.db"


class WorkspaceBundleError(RuntimeError):
    """Raised when a portable workspace bundle cannot be safely handled."""


def _resolve_path(base_dir: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base_dir / path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_metadata(path: Path) -> dict[str, Any]:
    return {"size": path.stat().st_size, "sha256": _sha256(path)}


def _validate_database(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise WorkspaceBundleError(f"Workspace bundle database is missing or empty: {path}")
    try:
        connection = sqlite3.connect(path)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise WorkspaceBundleError(f"Workspace bundle database is not valid SQLite: {path}") from exc
    if not integrity or integrity[0] != "ok":
        raise WorkspaceBundleError(f"Workspace bundle database failed integrity check: {path}")
    if "snapshot_runs" not in tables:
        raise WorkspaceBundleError("Workspace bundle database is missing the snapshot_runs table")


def _backup_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        source_connection = sqlite3.connect(source)
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
            destination_connection.commit()
        finally:
            destination_connection.close()
            source_connection.close()
    except sqlite3.DatabaseError as exc:
        raise WorkspaceBundleError(f"Could not copy the SQLite database safely: {source}") from exc


def _temporary_root(base_dir: Path) -> Path:
    root = base_dir / ".test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_archive(output: Path, stage: Path, manifest: dict[str, Any], members: list[str]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            for member in members:
                archive.write(stage / member, member)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def export_workspace_bundle(
    settings: Settings,
    output_path: str | Path,
    data_dir: str = "data",
    include_inputs: bool = True,
    min_rows: int = 500,
) -> dict[str, Any]:
    """Export SQLite state and optionally the four live CSV inputs."""
    base_dir = Path(settings.base_dir)
    output = _resolve_path(base_dir, output_path)
    database = Path(settings.db_path)
    if not database.is_file():
        raise WorkspaceBundleError(f"Active SQLite database does not exist: {database}")

    input_rows: dict[str, int] = {}
    input_source = _resolve_path(base_dir, data_dir)
    payload: dict[str, Any] | None = None
    if include_inputs:
        payload = load_csv_bundle(input_source)
        input_rows = validate_csv_bundle(input_source, min_rows=min_rows)

    with tempfile.TemporaryDirectory(
        prefix="workspace-bundle-",
        dir=_temporary_root(base_dir),
    ) as temporary_name:
        stage = Path(temporary_name)
        staged_database = stage / DATABASE_MEMBER
        _backup_database(database, staged_database)
        _validate_database(staged_database)

        members = [DATABASE_MEMBER]
        files: dict[str, dict[str, Any]] = {DATABASE_MEMBER: _file_metadata(staged_database)}
        if include_inputs and payload is not None:
            for filename in CSV_HEADERS:
                source = input_source / filename
                member = f"inputs/{filename}"
                target = stage / member
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                members.append(member)
                files[member] = _file_metadata(target)

        manifest = {
            "format": BUNDLE_FORMAT,
            "version": BUNDLE_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "includes_inputs": include_inputs,
            "input_rows": input_rows,
            "files": files,
        }
        _write_archive(output, stage, manifest, members)

    return {
        "bundle": str(output),
        "database": str(database),
        "includes_inputs": include_inputs,
        "rows": input_rows,
        "publication": "atomic",
    }


def _validate_archive_names(names: list[str]) -> None:
    if len(names) != len(set(names)):
        raise WorkspaceBundleError("Workspace bundle contains duplicate archive members")
    for name in names:
        path = PurePosixPath(name)
        windows_path = PureWindowsPath(name)
        if (
            not name
            or name.endswith("/")
            or "\\" in name
            or path.is_absolute()
            or windows_path.drive
            or windows_path.is_absolute()
            or ".." in path.parts
        ):
            raise WorkspaceBundleError(f"Workspace bundle contains an unsafe archive member: {name!r}")


def _read_manifest(archive: zipfile.ZipFile) -> tuple[dict[str, Any], list[str]]:
    names = archive.namelist()
    _validate_archive_names(names)
    if "manifest.json" not in names:
        raise WorkspaceBundleError("Workspace bundle is missing manifest.json")
    try:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
        raise WorkspaceBundleError("Workspace bundle manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise WorkspaceBundleError("Workspace bundle manifest must be an object")
    if manifest.get("format") != BUNDLE_FORMAT or manifest.get("version") != BUNDLE_VERSION:
        raise WorkspaceBundleError("Workspace bundle format or version is unsupported")
    includes_inputs = manifest.get("includes_inputs")
    if not isinstance(includes_inputs, bool):
        raise WorkspaceBundleError("Workspace bundle manifest has an invalid includes_inputs value")
    files = manifest.get("files")
    if not isinstance(files, dict) or DATABASE_MEMBER not in files:
        raise WorkspaceBundleError("Workspace bundle manifest does not describe the database")
    expected_files = {DATABASE_MEMBER}
    if includes_inputs:
        expected_files.update(f"inputs/{filename}" for filename in CSV_HEADERS)
    if set(files) != expected_files:
        raise WorkspaceBundleError("Workspace bundle manifest does not describe the expected files")
    expected_names = {"manifest.json", *expected_files}
    if set(names) != expected_names:
        raise WorkspaceBundleError("Workspace bundle contains unexpected files")
    return manifest, sorted(expected_files)


def _extract_members(archive: zipfile.ZipFile, stage: Path, manifest: dict[str, Any], members: list[str]) -> None:
    files = manifest["files"]
    for member in members:
        metadata = files.get(member)
        if not isinstance(metadata, dict) or not isinstance(metadata.get("size"), int) or not isinstance(
            metadata.get("sha256"), str
        ):
            raise WorkspaceBundleError(f"Workspace bundle has invalid metadata for {member}")
        target = stage / member
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(member))
        actual = _file_metadata(target)
        if actual != {"size": metadata["size"], "sha256": metadata["sha256"]}:
            raise WorkspaceBundleError(f"Workspace bundle checksum mismatch for {member}")


def _replace_staged_files(staged_targets: dict[Path, Path], rollback_dir: Path) -> None:
    rollback_dir.mkdir(parents=True, exist_ok=True)
    backups: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for target, staged in staged_targets.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                backup = rollback_dir / f"{len(backups):02d}-{target.name}.backup"
                shutil.copy2(target, backup)
                backups[target] = backup
            os.replace(staged, target)
            replaced.append(target)
    except Exception:
        for target in reversed(replaced):
            backup = backups.get(target)
            if backup and backup.exists():
                os.replace(backup, target)
            elif target.exists():
                target.unlink()
        raise


def _database_backup_path(settings: Settings) -> Path:
    backup_dir = Path(settings.data_dir) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return backup_dir / f"{Path(settings.db_path).stem}-before-bundle-import-{stamp}-{uuid.uuid4().hex[:8]}.db"


def import_workspace_bundle(
    settings: Settings,
    input_path: str | Path,
    data_dir: str = "data",
    replace_database: bool = False,
    min_rows: int = 500,
) -> dict[str, Any]:
    """Validate and restore a portable SQLite+CSV workspace bundle."""
    base_dir = Path(settings.base_dir)
    bundle = _resolve_path(base_dir, input_path)
    if not bundle.is_file():
        raise WorkspaceBundleError(f"Workspace bundle does not exist: {bundle}")

    database = Path(settings.db_path)
    database_existed = database.exists()
    if database_existed and not replace_database:
        raise WorkspaceBundleError(
            f"Active SQLite database already exists: {database}; rerun with --replace-database to restore it"
        )

    input_rows: dict[str, int] = {}
    destination = _resolve_path(base_dir, data_dir)
    durable_database_backup: Path | None = None
    with tempfile.TemporaryDirectory(
        prefix="workspace-bundle-import-",
        dir=_temporary_root(base_dir),
    ) as temporary_name:
        stage = Path(temporary_name)
        try:
            with zipfile.ZipFile(bundle, "r") as archive:
                manifest, members = _read_manifest(archive)
                _extract_members(archive, stage, manifest, members)
        except zipfile.BadZipFile as exc:
            raise WorkspaceBundleError(f"Workspace bundle is not a valid ZIP archive: {bundle}") from exc

        staged_database = stage / DATABASE_MEMBER
        _validate_database(staged_database)
        staged_targets: dict[Path, Path] = {}
        replacement = stage / "replacement"
        replacement.mkdir()

        if manifest["includes_inputs"]:
            input_source = stage / "inputs"
            input_rows = validate_csv_bundle(input_source, min_rows=min_rows)
            stage_extracted_tables(
                load_csv_bundle(input_source),
                staging=replacement,
                min_rows=min_rows,
            )
            for filename in CSV_HEADERS:
                staged_targets[destination / filename] = replacement / filename

        staged_database_target = replacement / "stock_expert.db"
        shutil.copy2(staged_database, staged_database_target)
        staged_targets[database] = staged_database_target

        if database_existed:
            durable_database_backup = _database_backup_path(settings)
            shutil.copy2(database, durable_database_backup)
        _replace_staged_files(staged_targets, rollback_dir=stage / "rollback")

    return {
        "bundle": str(bundle),
        "database": str(database),
        "database_replaced": database_existed,
        "database_backup": str(durable_database_backup) if durable_database_backup else None,
        "inputs_published": bool(manifest["includes_inputs"]),
        "rows": input_rows,
        "publication": "atomic",
    }
