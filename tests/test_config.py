import json

import pytest

from surveycto_module_library.config import (
    load_settings,
    normalize_server,
    save_selected_server,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("example", "example"),
        ("EXAMPLE.surveycto.com", "example"),
        ("https://example.surveycto.com/", "example"),
    ],
)
def test_normalize_server(value, expected):
    assert normalize_server(value) == expected


def test_normalize_server_rejects_invalid_values():
    with pytest.raises(ValueError):
        normalize_server("not a server!")


def test_saved_server_and_data_root_are_used(tmp_path):
    project_root = tmp_path / "project"
    data_root = tmp_path / "user-data"
    (project_root / "config").mkdir(parents=True)
    (project_root / "config" / "settings.toml").write_text(
        """
[surveycto]
server = "fallback"
[library]
database = "data/database/library.sqlite3"
raw_directory = "data/raw"
export_directory = "data/exports"
log_directory = "logs"
[classification]
provider = "rules"
external_models_enabled = false
""",
        encoding="utf-8",
    )
    save_selected_server(data_root, "https://chosen.surveycto.com")

    settings = load_settings(project_root, data_root)

    assert settings.server == "chosen"
    assert settings.server_configured is True
    assert settings.database_path == data_root / "data/database/library.sqlite3"
    assert json.loads((data_root / "settings.json").read_text())["server"] == "chosen"
