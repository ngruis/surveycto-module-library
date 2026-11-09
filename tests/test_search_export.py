from io import BytesIO

from openpyxl import load_workbook

from surveycto_module_library.database import initialize, replace_form, transaction
from surveycto_module_library.demo import _education_form
from surveycto_module_library.exporting import export_workbook
from surveycto_module_library.modules import infer_modules
from surveycto_module_library.parsing import parse_definition
from surveycto_module_library.search import SearchFilters, search_questions


def test_search_and_multisheet_export(tmp_path):
    database_path = tmp_path / "library.sqlite3"
    initialize(database_path)
    parsed = parse_definition(_education_form(), "fallback")
    with transaction(database_path) as connection:
        replace_form(
            connection,
            parsed,
            infer_modules(parsed),
            {},
            {},
            server="demo",
            run_id="test",
            content_hash="abc",
            raw_path=tmp_path / "raw.json",
            timestamp="now",
            processing_version="test-v1",
        )

    results = search_questions(database_path, SearchFilters(text="school"))
    assert len(results) == 3
    assert set(results["field_name"]) == {"enrolled", "days_absent", "highest_grade"}

    workbook = load_workbook(BytesIO(export_workbook(results)), read_only=True)
    assert workbook.sheetnames == ["Results", "Modules", "Questions", "Choices", "Metadata"]

    results.loc[results.index[0], "question_text"] = "x" * 40_000
    workbook = load_workbook(BytesIO(export_workbook(results)), read_only=True)
    header = [cell.value for cell in next(workbook["Results"].iter_rows())]
    question_text_column = header.index("question_text") + 1
    exported_text = workbook["Results"].cell(2, question_text_column).value
    assert len(exported_text) <= 32_767
    assert exported_text.endswith("[truncated in Excel]")
