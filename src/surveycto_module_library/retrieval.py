from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .credentials import Credentials

ProgressCallback = Callable[[int, int, int, int, int, str], None]


@dataclass(frozen=True)
class RetrievedDefinition:
    form_id: str
    payload: dict[str, Any]
    content_hash: str
    raw_path: Path
    retrieval_status: str = "downloaded"


class SurveyCTOApiRetriever:
    """Read deployed form definitions only; no submission endpoints are used."""

    def __init__(self, server: str, credentials: Credentials) -> None:
        self.server = server
        self.credentials = credentials
        self._definition_client = None

    def list_form_ids(self) -> list[str]:
        response = requests.get(
            f"https://{self.server}.surveycto.com/api/v2/forms/ids",
            auth=(self.credentials.username, self.credentials.password),
            timeout=90,
        )
        response.raise_for_status()
        return _extract_form_ids(response.json())

    def get_definition(self, form_id: str) -> dict[str, Any]:
        try:
            import pysurveycto
        except ImportError as exc:
            raise RuntimeError(
                "pysurveycto is required for SurveyCTO definition retrieval."
            ) from exc
        if self._definition_client is None:
            self._definition_client = pysurveycto.SurveyCTOObject(
                self.server, self.credentials.username, self.credentials.password
            )
        payload = self._definition_client.get_form_definition(form_id)
        if not isinstance(payload, dict):
            raise TypeError(
                f"Unexpected definition response for {form_id}: {type(payload).__name__}"
            )
        return payload

    def retrieve_all(
        self,
        raw_root: Path,
        run_id: str,
        form_ids: Iterable[str] | None = None,
        limit: int | None = None,
        reuse_existing: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[list[RetrievedDefinition], list[tuple[str, str]]]:
        ids = list(form_ids) if form_ids is not None else self.list_form_ids()
        if limit is not None:
            ids = ids[:limit]
        run_dir = raw_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        roster = build_raw_roster(raw_root, exclude_run_id=run_id) if reuse_existing else {}
        definitions: list[RetrievedDefinition] = []
        failures: list[tuple[str, str]] = []
        downloaded = 0
        reused = 0
        for position, form_id in enumerate(ids, start=1):
            existing_path = roster.get(form_id)
            if existing_path is not None:
                definitions.append(load_raw_definition(existing_path, retrieval_status="reused"))
                reused += 1
                _render_progress(position, len(ids), downloaded, reused, len(failures), form_id)
                if progress_callback:
                    progress_callback(position, len(ids), downloaded, reused, len(failures), form_id)
                continue
            try:
                payload = self.get_definition(form_id)
                encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
                digest = hashlib.sha256(encoded).hexdigest()
                path = run_dir / f"{_safe_name(form_id)}__{digest[:12]}.json"
                envelope = {
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "server": self.server,
                    "form_id": form_id,
                    "sha256": digest,
                    "definition": payload,
                }
                path.write_text(
                    json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                definitions.append(RetrievedDefinition(form_id, payload, digest, path))
                downloaded += 1
            except Exception as exc:  # noqa: BLE001 - preserve useful partial full-server runs
                failures.append((form_id, str(exc)))
            _render_progress(position, len(ids), downloaded, reused, len(failures), form_id)
            if progress_callback:
                progress_callback(position, len(ids), downloaded, reused, len(failures), form_id)
        if ids:
            print()
        for form_id, error in failures:
            print(f"Failed to download {form_id}: {error}")
        return definitions, failures


def load_raw_definition(
    payload_path: Path, retrieval_status: str = "downloaded"
) -> RetrievedDefinition:
    envelope = json.loads(payload_path.read_text(encoding="utf-8"))
    payload = envelope.get("definition", envelope)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return RetrievedDefinition(
        form_id=str(envelope.get("form_id") or payload.get("formId") or payload_path.stem),
        payload=payload,
        content_hash=str(envelope.get("sha256") or hashlib.sha256(encoded).hexdigest()),
        raw_path=payload_path,
        retrieval_status=retrieval_status,
    )


def build_raw_roster(raw_root: Path, exclude_run_id: str | None = None) -> dict[str, Path]:
    """Return the newest usable raw JSON path for every previously archived form ID."""
    if not raw_root.exists():
        return {}
    roster: dict[str, Path] = {}
    run_directories = sorted(
        (path for path in raw_root.iterdir() if path.is_dir() and path.name != exclude_run_id),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    # Newer runs provide a fast complete roster, including definitions reused from older runs.
    for run_dir in run_directories:
        metadata_path = run_dir / "run_metadata.json"
        if not metadata_path.exists():
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            for item in metadata.get("definitions", []):
                form_id = str(item.get("form_id", ""))
                raw_path = raw_root / str(item.get("raw_path", ""))
                if form_id and raw_path.is_file():
                    roster.setdefault(form_id, raw_path)
        except (OSError, TypeError, ValueError):
            continue

    # Legacy archives have no manifest, so inspect their definition envelopes once.
    for run_dir in run_directories:
        for payload_path in run_dir.glob("*__*.json"):
            try:
                definition = load_raw_definition(payload_path, retrieval_status="reused")
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            roster.setdefault(definition.form_id, payload_path)
    return roster


def definition_paths_for_run(raw_root: Path, run_dir: Path) -> list[Path]:
    """Resolve a complete run snapshot, including JSON reused from prior archives."""
    metadata_path = run_dir / "run_metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        paths = [raw_root / str(item["raw_path"]) for item in metadata.get("definitions", [])]
        return [path for path in paths if path.is_file()]
    return sorted(run_dir.glob("*__*.json"))


def _render_progress(
    completed: int,
    total: int,
    downloaded: int,
    reused: int,
    failed: int,
    form_id: str,
) -> None:
    width = 28
    filled = width if total == 0 else int(width * completed / total)
    bar = "#" * filled + "-" * (width - filled)
    percent = 100 if total == 0 else int(100 * completed / total)
    label = form_id if len(form_id) <= 32 else form_id[:29] + "..."
    line = (
        f"\r[{bar}] {percent:3d}% {completed}/{total} "
        f"downloaded={downloaded} reused={reused} failed={failed} {label:<32}"
    )
    print(line, end="", flush=True, file=sys.stdout)


def _extract_form_ids(payload: object) -> list[str]:
    if isinstance(payload, list):
        return [
            str(item.get("formId") or item.get("id")) if isinstance(item, dict) else str(item)
            for item in payload
        ]
    if isinstance(payload, dict):
        for key in ("data", "formIds", "forms", "ids"):
            value = payload.get(key)
            if isinstance(value, list):
                return _extract_form_ids(value)
    raise RuntimeError("SurveyCTO returned an unfamiliar form-list response.")


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)[:120]
