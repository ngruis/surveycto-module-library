from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .categorization import CategoryMatch
from .modules import InferredModule
from .parsing import ParsedDefinition

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS scrape_runs (
  id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
  forms_found INTEGER DEFAULT 0, forms_downloaded INTEGER DEFAULT 0, forms_reused INTEGER DEFAULT 0,
  forms_failed INTEGER DEFAULT 0,
  forms_parsed INTEGER DEFAULT 0, questions INTEGER DEFAULT 0, choices INTEGER DEFAULT 0,
  source_groups INTEGER DEFAULT 0, inferred_modules INTEGER DEFAULT 0,
  categorized_questions INTEGER DEFAULT 0, uncategorized_questions INTEGER DEFAULT 0,
  dependencies INTEGER DEFAULT 0, error_summary TEXT
);
CREATE TABLE IF NOT EXISTS forms (
  form_id TEXT PRIMARY KEY, title TEXT NOT NULL, version TEXT, default_language TEXT,
  server TEXT NOT NULL, source_url TEXT, content_hash TEXT NOT NULL,
  first_seen_run_id TEXT NOT NULL, last_seen_run_id TEXT NOT NULL, updated_at TEXT NOT NULL,
  processing_version TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS raw_form_definitions (
  id INTEGER PRIMARY KEY, form_id TEXT NOT NULL, scrape_run_id TEXT NOT NULL, content_hash TEXT NOT NULL,
  raw_path TEXT NOT NULL, retrieved_at TEXT NOT NULL, UNIQUE(form_id, content_hash)
);
CREATE TABLE IF NOT EXISTS survey_questions (
  stable_id TEXT PRIMARY KEY, form_id TEXT NOT NULL, row_order INTEGER NOT NULL, excel_row INTEGER NOT NULL,
  field_name TEXT NOT NULL, field_type TEXT, base_type TEXT, choice_list_name TEXT,
  labels_json TEXT NOT NULL, hints_json TEXT NOT NULL, search_text TEXT NOT NULL,
  relevance TEXT, constraint_expression TEXT, calculation TEXT, appearance TEXT, required TEXT,
  is_question INTEGER NOT NULL, is_note INTEGER NOT NULL, is_noise INTEGER NOT NULL DEFAULT 0,
  source_group_id TEXT, group_path_json TEXT NOT NULL, raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_questions_form ON survey_questions(form_id, row_order);
CREATE TABLE IF NOT EXISTS choice_lists (
  stable_id TEXT PRIMARY KEY, form_id TEXT NOT NULL, list_name TEXT NOT NULL, UNIQUE(form_id, list_name)
);
CREATE TABLE IF NOT EXISTS choices (
  id INTEGER PRIMARY KEY, choice_list_id TEXT NOT NULL, row_order INTEGER NOT NULL, value TEXT,
  labels_json TEXT NOT NULL, raw_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_groups (
  stable_id TEXT PRIMARY KEY, form_id TEXT NOT NULL, name TEXT NOT NULL, label TEXT, kind TEXT NOT NULL,
  start_order INTEGER NOT NULL, end_order INTEGER NOT NULL, parent_stable_id TEXT, depth INTEGER NOT NULL,
  question_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS inferred_modules (
  stable_id TEXT PRIMARY KEY, form_id TEXT NOT NULL, name TEXT NOT NULL, label TEXT NOT NULL,
  source_group_id TEXT, start_order INTEGER NOT NULL, end_order INTEGER NOT NULL,
  inference_method TEXT NOT NULL, confidence REAL NOT NULL, is_noise INTEGER NOT NULL,
  human_status TEXT, human_label TEXT
);
CREATE TABLE IF NOT EXISTS module_questions (
  module_id TEXT NOT NULL, question_id TEXT NOT NULL, position INTEGER NOT NULL,
  PRIMARY KEY(module_id, question_id)
);
CREATE INDEX IF NOT EXISTS idx_module_questions_question ON module_questions(question_id);
CREATE TABLE IF NOT EXISTS dependencies (
  id INTEGER PRIMARY KEY, form_id TEXT NOT NULL, question_id TEXT NOT NULL,
  dependency_type TEXT NOT NULL, target TEXT NOT NULL, source_column TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dependencies_question ON dependencies(question_id);
CREATE TABLE IF NOT EXISTS taxonomy_terms (
  id INTEGER PRIMARY KEY, topic TEXT NOT NULL, subtopic TEXT NOT NULL, term TEXT NOT NULL,
  UNIQUE(topic, subtopic, term)
);
CREATE TABLE IF NOT EXISTS question_categories (
  id INTEGER PRIMARY KEY, question_id TEXT NOT NULL, topic TEXT NOT NULL, subtopic TEXT NOT NULL,
  score REAL NOT NULL, method TEXT NOT NULL, model TEXT, evidence_json TEXT NOT NULL,
  is_human INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_question_categories ON question_categories(topic, subtopic);
CREATE INDEX IF NOT EXISTS idx_question_categories_question_score
  ON question_categories(question_id, score DESC);
CREATE TABLE IF NOT EXISTS module_categories (
  id INTEGER PRIMARY KEY, module_id TEXT NOT NULL, topic TEXT NOT NULL, subtopic TEXT NOT NULL,
  score REAL NOT NULL, method TEXT NOT NULL, evidence_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT
);
CREATE TABLE IF NOT EXISTS form_projects (
  form_id TEXT NOT NULL, project_id INTEGER NOT NULL, PRIMARY KEY(form_id, project_id)
);
CREATE TABLE IF NOT EXISTS population_metadata (
  id INTEGER PRIMARY KEY, project_id INTEGER, form_id TEXT, key TEXT NOT NULL, value TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'human', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS classification_runs (
  id TEXT PRIMARY KEY, scrape_run_id TEXT, started_at TEXT NOT NULL, finished_at TEXT,
  provider TEXT NOT NULL, model TEXT, status TEXT NOT NULL, items_classified INTEGER DEFAULT 0,
  failures INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS semantic_embeddings (
  id INTEGER PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
  provider TEXT NOT NULL, model TEXT NOT NULL, dimensions INTEGER NOT NULL,
  vector BLOB NOT NULL, content_hash TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(entity_type, entity_id, provider, model)
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(path: Path) -> None:
    with connect(path) as connection:
        connection.executescript(SCHEMA)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(forms)")}
        if "processing_version" not in columns:
            connection.execute(
                "ALTER TABLE forms ADD COLUMN processing_version TEXT NOT NULL DEFAULT ''"
            )
        run_columns = {row[1] for row in connection.execute("PRAGMA table_info(scrape_runs)")}
        if "forms_reused" not in run_columns:
            connection.execute(
                "ALTER TABLE scrape_runs ADD COLUMN forms_reused INTEGER NOT NULL DEFAULT 0"
            )


@contextmanager
def transaction(path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(path)
    try:
        connection.execute("BEGIN")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def replace_form(
    connection: sqlite3.Connection,
    parsed: ParsedDefinition,
    modules: list[InferredModule],
    question_categories: dict[str, list[CategoryMatch]],
    module_categories: dict[str, list[CategoryMatch]],
    *,
    server: str,
    run_id: str,
    content_hash: str,
    raw_path: Path,
    timestamp: str,
    processing_version: str,
) -> None:
    existing = connection.execute(
        "SELECT first_seen_run_id FROM forms WHERE form_id = ?", (parsed.form_id,)
    ).fetchone()
    first_seen = existing["first_seen_run_id"] if existing else run_id
    for table, column in (
        ("question_categories", "question_id"),
        ("module_questions", "question_id"),
        ("dependencies", "form_id"),
        ("choices", "choice_list_id"),
        ("module_categories", "module_id"),
        ("inferred_modules", "form_id"),
        ("source_groups", "form_id"),
        ("survey_questions", "form_id"),
        ("choice_lists", "form_id"),
    ):
        if table in {"question_categories", "module_questions"}:
            connection.execute(
                f"DELETE FROM {table} WHERE {column} IN (SELECT stable_id FROM survey_questions WHERE form_id = ?)",
                (parsed.form_id,),
            )
        elif table in {"module_categories"}:
            connection.execute(
                f"DELETE FROM {table} WHERE {column} IN (SELECT stable_id FROM inferred_modules WHERE form_id = ?)",
                (parsed.form_id,),
            )
        elif table == "choices":
            connection.execute(
                "DELETE FROM choices WHERE choice_list_id IN (SELECT stable_id FROM choice_lists WHERE form_id = ?)",
                (parsed.form_id,),
            )
        else:
            connection.execute(f"DELETE FROM {table} WHERE {column} = ?", (parsed.form_id,))

    connection.execute(
        """INSERT OR REPLACE INTO forms
        (form_id,title,version,default_language,server,source_url,content_hash,first_seen_run_id,
        last_seen_run_id,updated_at,processing_version)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            parsed.form_id,
            parsed.title,
            parsed.version,
            parsed.default_language,
            server,
            f"https://{server}.surveycto.com/#Design",
            content_hash,
            first_seen,
            run_id,
            timestamp,
            processing_version,
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO raw_form_definitions(form_id,scrape_run_id,content_hash,raw_path,retrieved_at) VALUES (?,?,?,?,?)",
        (parsed.form_id, run_id, content_hash, str(raw_path), timestamp),
    )
    for group in parsed.groups:
        connection.execute(
            "INSERT INTO source_groups VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                group.stable_id,
                parsed.form_id,
                group.name,
                group.label,
                group.kind,
                group.start_order,
                group.end_order,
                group.parent_stable_id,
                group.depth,
                group.question_count,
            ),
        )
    for question in parsed.questions:
        labels_json = _json(question.labels)
        hints_json = _json(question.hints)
        search_text = " ".join(
            [question.field_name, *question.labels.values(), *question.hints.values()]
        )
        connection.execute(
            """INSERT INTO survey_questions VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                question.stable_id,
                parsed.form_id,
                question.row_order,
                question.excel_row,
                question.field_name,
                question.field_type,
                question.base_type,
                question.choice_list_name,
                labels_json,
                hints_json,
                search_text,
                question.relevance,
                question.constraint,
                question.calculation,
                question.appearance,
                question.required,
                int(question.is_question),
                int(question.is_note),
                0,
                question.source_group_id,
                _json(question.group_path),
                _json(question.raw),
            ),
        )
        for match in question_categories.get(question.stable_id, []):
            connection.execute(
                "INSERT INTO question_categories(question_id,topic,subtopic,score,method,evidence_json) VALUES (?,?,?,?,?,?)",
                (
                    question.stable_id,
                    match.topic,
                    match.subtopic,
                    match.score,
                    match.method,
                    _json(match.matched_terms),
                ),
            )
    lists: dict[str, str] = {}
    for choice in parsed.choices:
        list_id = lists.setdefault(choice.list_name, f"{parsed.form_id}:choices:{choice.list_name}")
        connection.execute(
            "INSERT OR IGNORE INTO choice_lists VALUES (?,?,?)",
            (list_id, parsed.form_id, choice.list_name),
        )
        connection.execute(
            "INSERT INTO choices(choice_list_id,row_order,value,labels_json,raw_json) VALUES (?,?,?,?,?)",
            (list_id, choice.row_order, choice.value, _json(choice.labels), _json(choice.raw)),
        )
    for dependency in parsed.dependencies:
        connection.execute(
            "INSERT INTO dependencies(form_id,question_id,dependency_type,target,source_column) VALUES (?,?,?,?,?)",
            (
                parsed.form_id,
                dependency.question_stable_id,
                dependency.dependency_type,
                dependency.target,
                dependency.source_column,
            ),
        )
    for module in modules:
        connection.execute(
            "INSERT INTO inferred_modules(stable_id,form_id,name,label,source_group_id,start_order,end_order,inference_method,confidence,is_noise) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                module.stable_id,
                parsed.form_id,
                module.name,
                module.label,
                module.source_group_id,
                module.start_order,
                module.end_order,
                module.inference_method,
                module.confidence,
                int(module.is_noise),
            ),
        )
        for position, question_id in enumerate(module.question_ids, start=1):
            connection.execute(
                "INSERT INTO module_questions VALUES (?,?,?)",
                (module.stable_id, question_id, position),
            )
        for match in module_categories.get(module.stable_id, []):
            connection.execute(
                "INSERT INTO module_categories(module_id,topic,subtopic,score,method,evidence_json) VALUES (?,?,?,?,?,?)",
                (
                    module.stable_id,
                    match.topic,
                    match.subtopic,
                    match.score,
                    match.method,
                    _json(match.matched_terms),
                ),
            )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
