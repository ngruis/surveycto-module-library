from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

PROJECT_ROOT = (
    Path(sys._MEIPASS)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
    else Path(__file__).resolve().parents[2]
)


@dataclass(frozen=True)
class Settings:
    root: Path
    server: str
    database_path: Path
    raw_directory: Path
    export_directory: Path
    log_directory: Path
    taxonomy_path: Path
    classification_provider: str
    external_models_enabled: bool
    data_root: Path | None = None
    server_configured: bool = True

    @property
    def server_url(self) -> str:
        return f"https://{self.server}.surveycto.com"

    @property
    def storage_root(self) -> Path:
        return self.data_root or self.root


def load_settings(root: Path | None = None, data_root: Path | None = None) -> Settings:
    root = (root or PROJECT_ROOT).resolve()
    data_root = (data_root or _default_data_root(root)).resolve()
    config_path = root / "config" / "settings.toml"
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    surveycto = raw.get("surveycto", {})
    library = raw.get("library", {})
    classification = raw.get("classification", {})
    saved = _load_user_settings(data_root)
    configured_server = os.getenv("SURVEYCTO_SERVER") or saved.get("server")
    server = configured_server or str(surveycto.get("server", "jpalmena"))
    return Settings(
        root=root,
        server=normalize_server(server),
        database_path=data_root / library.get("database", "data/database/module_library.sqlite3"),
        raw_directory=data_root / library.get("raw_directory", "data/raw"),
        export_directory=data_root / library.get("export_directory", "data/exports"),
        log_directory=data_root / library.get("log_directory", "logs"),
        taxonomy_path=root / "config" / "taxonomy.json",
        classification_provider=str(classification.get("provider", "rules")),
        external_models_enabled=bool(classification.get("external_models_enabled", False)),
        data_root=data_root,
        server_configured=bool(configured_server),
    )


def normalize_server(value: str) -> str:
    server = value.strip().lower()
    for prefix in ("https://", "http://"):
        server = server.removeprefix(prefix)
    server = server.split("/", 1)[0]
    server = server.removesuffix(".surveycto.com")
    if not server or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in server):
        raise ValueError("Enter a SurveyCTO server name such as example or example.surveycto.com.")
    return server


def save_selected_server(data_root: Path, server: str) -> Path:
    data_root.mkdir(parents=True, exist_ok=True)
    path = data_root / "settings.json"
    path.write_text(
        json.dumps({"server": normalize_server(server)}, indent=2), encoding="utf-8"
    )
    return path


def _load_user_settings(data_root: Path) -> dict[str, str]:
    path = data_root / "settings.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _default_data_root(project_root: Path) -> Path:
    override = os.getenv("SURVEYCTO_LIBRARY_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if getattr(sys, "frozen", False):
        return Path(user_data_path("SurveyCTO Module Library", "J-PAL MENA"))
    return project_root
