import sqlite3

from surveycto_module_library.database import initialize, replace_form, transaction
from surveycto_module_library.demo import _education_form
from surveycto_module_library.modules import infer_modules
from surveycto_module_library.parsing import parse_definition


def test_database_round_trip(tmp_path):
    database_path = tmp_path / "library.sqlite3"
    initialize(database_path)
    parsed = parse_definition(_education_form(), "fallback")
    modules = infer_modules(parsed)
    with transaction(database_path) as connection:
        replace_form(
            connection,
            parsed,
            modules,
            {},
            {},
            server="demo",
            run_id="test",
            content_hash="abc",
            raw_path=tmp_path / "raw.json",
            timestamp="now",
            processing_version="test-v1",
        )
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM forms").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM survey_questions WHERE is_question=1"
            ).fetchone()[0]
            == 5
        )
        assert connection.execute("SELECT COUNT(*) FROM inferred_modules").fetchone()[0] == 2
