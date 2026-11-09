import hashlib
import json

from surveycto_module_library.config import Settings
from surveycto_module_library.pipeline import ValidationSummary, _write_run_metadata
from surveycto_module_library.retrieval import (
    RetrievedDefinition,
    SurveyCTOApiRetriever,
    build_raw_roster,
    definition_paths_for_run,
)


def _write_definition(path, form_id, payload):
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "retrieved_at": "2026-01-01T00:00:00+00:00",
                "server": "test",
                "form_id": form_id,
                "sha256": digest,
                "definition": payload,
            }
        ),
        encoding="utf-8",
    )
    return digest


class FakeRetriever(SurveyCTOApiRetriever):
    def __init__(self, payloads):
        self.server = "test"
        self.payloads = payloads
        self.calls = []

    def get_definition(self, form_id):
        self.calls.append(form_id)
        return self.payloads[form_id]


def test_retrieve_all_reuses_existing_form_ids_and_shows_progress(tmp_path, capsys):
    raw_root = tmp_path / "raw"
    old_payload = {"formId": "old_form", "surveyRowsAndColumns": []}
    old_path = raw_root / "run_old" / "old_form__abc.json"
    _write_definition(old_path, "old_form", old_payload)

    new_payload = {"formId": "new_form", "surveyRowsAndColumns": []}
    retriever = FakeRetriever({"new_form": new_payload})
    definitions, failures = retriever.retrieve_all(
        raw_root,
        "run_new",
        form_ids=["old_form", "new_form"],
    )

    assert failures == []
    assert retriever.calls == ["new_form"]
    assert {item.form_id for item in definitions} == {"old_form", "new_form"}
    assert {item.form_id for item in definitions if item.retrieval_status == "reused"} == {
        "old_form"
    }
    assert len(list((raw_root / "run_new").glob("*__*.json"))) == 1
    output = capsys.readouterr().out
    assert "100%" in output
    assert "downloaded=1 reused=1 failed=0" in output


def test_run_metadata_is_a_complete_rebuild_roster(tmp_path):
    root = tmp_path / "library"
    raw_root = root / "data" / "raw"
    old_path = raw_root / "run_old" / "old_form__abc.json"
    new_path = raw_root / "run_new" / "new_form__def.json"
    old_hash = _write_definition(old_path, "old_form", {"formId": "old_form"})
    new_hash = _write_definition(new_path, "new_form", {"formId": "new_form"})
    settings = Settings(
        root=root,
        server="test",
        database_path=root / "data" / "database.sqlite3",
        raw_directory=raw_root,
        export_directory=root / "data" / "exports",
        log_directory=root / "logs",
        taxonomy_path=root / "config" / "taxonomy.json",
        classification_provider="rules",
        external_models_enabled=False,
    )
    definitions = [
        RetrievedDefinition("old_form", {}, old_hash, old_path, "reused"),
        RetrievedDefinition("new_form", {}, new_hash, new_path, "downloaded"),
    ]
    summary = ValidationSummary(
        run_id="run_new",
        forms_found=2,
        forms_downloaded=1,
        forms_reused=1,
        parsed_forms=1,
        unchanged_forms=1,
        failures=[],
    )

    metadata_path = _write_run_metadata(
        settings,
        summary,
        definitions,
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:01:00+00:00",
        "success",
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert metadata["retrieval"]["downloaded_form_ids"] == ["new_form"]
    assert metadata["retrieval"]["reused_form_ids"] == ["old_form"]
    assert metadata["processing"]["unchanged_forms"] == 1
    assert definition_paths_for_run(raw_root, raw_root / "run_new") == [new_path, old_path]
    assert build_raw_roster(raw_root) == {"new_form": new_path, "old_form": old_path}
