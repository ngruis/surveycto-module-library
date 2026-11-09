from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .database import connect


@dataclass(frozen=True)
class SearchFilters:
    text: str = ""
    topics: list[str] = field(default_factory=list)
    subtopics: list[str] = field(default_factory=list)
    forms: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    question_types: list[str] = field(default_factory=list)
    include_noise: bool = False


def filter_options(database_path: Path) -> dict[str, list[str]]:
    empty = {
        key: []
        for key in ("topics", "subtopics", "forms", "modules", "languages", "question_types")
    }
    if not database_path.exists():
        return empty
    with connect(database_path) as connection:
        options = {
            "topics": _column(
                connection, "SELECT DISTINCT topic FROM question_categories ORDER BY topic"
            ),
            "subtopics": _column(
                connection, "SELECT DISTINCT subtopic FROM question_categories ORDER BY subtopic"
            ),
            "forms": _column(
                connection, "SELECT form_id || ' — ' || title FROM forms ORDER BY title"
            ),
            "modules": _column(
                connection,
                "SELECT DISTINCT label FROM inferred_modules WHERE is_noise=0 ORDER BY label",
            ),
            "question_types": _column(
                connection,
                "SELECT DISTINCT base_type FROM survey_questions WHERE is_question=1 ORDER BY base_type",
            ),
        }
        languages: set[str] = set()
        for row in connection.execute("SELECT labels_json FROM survey_questions"):
            languages.update(_loads(row[0], {}).keys())
        options["languages"] = sorted(languages)
        return options


def search_questions(database_path: Path, filters: SearchFilters) -> pd.DataFrame:
    if not database_path.exists():
        return pd.DataFrame()
    where = ["q.is_question = 1"]
    params: list[object] = []
    if not filters.include_noise:
        where.append("COALESCE(m.is_noise, 0) = 0")
    if filters.text:
        where.append("LOWER(q.search_text || ' ' || COALESCE(m.label,'')) LIKE ?")
        params.append(f"%{filters.text.casefold()}%")
    _add_in(where, params, "qc.topic", filters.topics)
    _add_in(where, params, "qc.subtopic", filters.subtopics)
    _add_in(where, params, "q.form_id", [value.split(" — ", 1)[0] for value in filters.forms])
    _add_in(where, params, "m.label", filters.modules)
    _add_in(where, params, "q.base_type", filters.question_types)
    if filters.languages:
        where.append("(" + " OR ".join("q.labels_json LIKE ?" for _ in filters.languages) + ")")
        params.extend(f'%"{language}"%' for language in filters.languages)
    sql = f"""
    WITH ranked_categories AS (
      SELECT question_id, topic, subtopic, score,
        ROW_NUMBER() OVER (
          PARTITION BY question_id ORDER BY score DESC, topic, subtopic
        ) AS rank
      FROM question_categories
    )
    SELECT q.stable_id, q.form_id, f.title AS survey, f.version, f.source_url,
      COALESCE(m.human_label,m.label,'Ungrouped questions') AS module,
      m.stable_id AS module_id, q.row_order, q.excel_row, q.field_name, q.field_type,
      q.base_type,
      q.labels_json, q.hints_json, q.choice_list_name, q.relevance,
      q.constraint_expression AS constraint_text, q.calculation, q.appearance, q.required,
      q.group_path_json, qc.topic, qc.subtopic, qc.score AS category_score
    FROM survey_questions q
    JOIN forms f ON f.form_id=q.form_id
    LEFT JOIN module_questions mq ON mq.question_id=q.stable_id
    LEFT JOIN inferred_modules m ON m.stable_id=mq.module_id
    LEFT JOIN ranked_categories qc ON qc.question_id=q.stable_id AND qc.rank=1
    WHERE {" AND ".join(where)}
    GROUP BY q.stable_id, m.stable_id
    ORDER BY f.title, m.start_order, q.row_order
    """
    with connect(database_path) as connection:
        frame = pd.read_sql_query(sql, connection, params=params)
        if frame.empty:
            return frame
        choice_map = _choice_map(connection, frame)
        dependency_map = _dependency_map(connection, frame["stable_id"].tolist())
    frame["labels"] = frame["labels_json"].map(lambda value: _loads(value, {}))
    frame["hints"] = frame["hints_json"].map(lambda value: _loads(value, {}))
    frame["group_path"] = frame["group_path_json"].map(lambda value: _loads(value, []))
    frame["question_text"] = frame["labels"].map(lambda values: next(iter(values.values()), ""))
    frame["language"] = frame["labels"].map(lambda values: ", ".join(values.keys()))
    frame["choices"] = frame.apply(
        lambda row: choice_map.get((row.form_id, row.choice_list_name), []), axis=1
    )
    frame["dependencies"] = frame["stable_id"].map(lambda value: dependency_map.get(value, []))
    return frame


def _choice_map(
    connection: sqlite3.Connection, frame: pd.DataFrame
) -> dict[tuple[str, str], list[dict]]:
    result: dict[tuple[str, str], list[dict]] = {}
    form_ids = frame["form_id"].dropna().unique().tolist()
    if not form_ids:
        return result
    placeholders = ",".join("?" for _ in form_ids)
    rows = connection.execute(
        f"""SELECT cl.form_id,cl.list_name,c.value,c.labels_json FROM choice_lists cl
        JOIN choices c ON c.choice_list_id=cl.stable_id
        WHERE cl.form_id IN ({placeholders}) ORDER BY c.row_order""",
        form_ids,
    )
    for row in rows:
        result.setdefault((row[0], row[1]), []).append(
            {"value": row[2], "labels": _loads(row[3], {})}
        )
    return result


def _dependency_map(
    connection: sqlite3.Connection, question_ids: list[str]
) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for start in range(0, len(question_ids), 800):
        chunk = question_ids[start : start + 800]
        placeholders = ",".join("?" for _ in chunk)
        rows = connection.execute(
            f"""SELECT question_id,dependency_type,target,source_column FROM dependencies
            WHERE question_id IN ({placeholders})""",
            chunk,
        )
        for row in rows:
            result.setdefault(row[0], []).append(
                {"type": row[1], "target": row[2], "column": row[3]}
            )
    return result


def _column(connection: sqlite3.Connection, sql: str) -> list[str]:
    return [str(row[0]) for row in connection.execute(sql) if row[0] not in (None, "")]


def _add_in(where: list[str], params: list[object], column: str, values: list[str]) -> None:
    if values:
        where.append(f"{column} IN ({','.join('?' for _ in values)})")
        params.extend(values)


def _loads(value: str, fallback):
    try:
        return json.loads(value or "")
    except (json.JSONDecodeError, TypeError):
        return fallback
