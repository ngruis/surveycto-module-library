from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

FIELD_REF = re.compile(r"\$\{([^}]+)\}")
PULLDATA = re.compile(r"pulldata\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
SEARCH = re.compile(r"search\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
PLUGIN = re.compile(r"(?:^|\s)custom-([A-Za-z0-9_.-]+)", re.IGNORECASE)
MEDIA = re.compile(
    r"(?:^|[\s'\"])([^\s'\"]+\.(?:csv|jpg|jpeg|png|gif|mp3|wav|mp4|pdf|fieldplugin\.zip))",
    re.IGNORECASE,
)
SELECT_TYPE = re.compile(r"^select_(?:one|multiple)(?:_from_file)?\s+(.+)$", re.IGNORECASE)
STRUCTURAL_TYPES = {"begin group", "end group", "begin repeat", "end repeat"}
NON_QUESTION_PREFIXES = (
    "calculate",
    "metadata",
    "deviceid",
    "subscriberid",
    "simserial",
    "phonenumber",
    "start",
    "end",
    "today",
    "username",
    "caseid",
    "text audit",
    "audio audit",
    "speed violations",
    "sensor_",
)


@dataclass
class ParsedChoice:
    list_name: str
    value: str
    labels: dict[str, str]
    row_order: int
    raw: dict[str, Any]


@dataclass
class ParsedGroup:
    stable_id: str
    name: str
    label: str
    kind: str
    start_order: int
    end_order: int
    parent_stable_id: str | None
    depth: int
    question_count: int = 0


@dataclass
class ParsedQuestion:
    stable_id: str
    row_order: int
    excel_row: int
    field_name: str
    field_type: str
    base_type: str
    choice_list_name: str | None
    labels: dict[str, str]
    hints: dict[str, str]
    relevance: str
    constraint: str
    calculation: str
    appearance: str
    required: str
    is_question: bool
    is_note: bool
    source_group_id: str | None
    group_path: list[str]
    raw: dict[str, Any]


@dataclass
class ParsedDependency:
    question_stable_id: str
    dependency_type: str
    target: str
    source_column: str


@dataclass
class ParsedDefinition:
    form_id: str
    title: str
    version: str
    default_language: str
    settings: dict[str, Any]
    questions: list[ParsedQuestion] = field(default_factory=list)
    choices: list[ParsedChoice] = field(default_factory=list)
    groups: list[ParsedGroup] = field(default_factory=list)
    dependencies: list[ParsedDependency] = field(default_factory=list)


def parse_definition(payload: dict[str, Any], fallback_form_id: str) -> ParsedDefinition:
    survey_rows = _matrix_to_records(
        payload.get("fieldsRowsAndColumns") or payload.get("survey") or []
    )
    choice_rows = _matrix_to_records(
        payload.get("choicesRowsAndColumns") or payload.get("choices") or []
    )
    setting_rows = _matrix_to_records(
        payload.get("settingsRowsAndColumns") or payload.get("settings") or []
    )
    settings = {
        k: v for k, v in (setting_rows[0] if setting_rows else {}).items() if not k.startswith("_")
    }
    form_id = str(
        settings.get("form_id") or payload.get("formId") or payload.get("id") or fallback_form_id
    )
    title = str(settings.get("form_title") or payload.get("title") or form_id)
    version = str(settings.get("version") or payload.get("version") or "")
    default_language = _normalize_language(settings.get("default_language") or "Default")

    parsed = ParsedDefinition(form_id, title, version, default_language, settings)
    for row in choice_rows:
        list_name = _text(row.get("list_name"))
        value = _text(row.get("value"))
        if list_name:
            parsed.choices.append(
                ParsedChoice(
                    list_name,
                    value,
                    _language_values(row, "label", default_language),
                    int(row["_row"]),
                    row,
                )
            )

    stack: list[tuple[ParsedGroup, int]] = []
    for position, row in enumerate(survey_rows, start=1):
        row_type = _text(row.get("type")).lower().replace("_", " ")
        name = _text(row.get("name"))
        if row_type in {"begin group", "begin repeat"}:
            group = ParsedGroup(
                stable_id=f"{form_id}:group:{position}:{name or 'unnamed'}",
                name=name or f"group_{position}",
                label=_best_text(_language_values(row, "label", default_language), name),
                kind="repeat" if row_type == "begin repeat" else "group",
                start_order=position,
                end_order=position,
                parent_stable_id=stack[-1][0].stable_id if stack else None,
                depth=len(stack),
            )
            parsed.groups.append(group)
            stack.append((group, position))
            continue
        if row_type in {"end group", "end repeat"}:
            if stack:
                group, _ = stack.pop()
                group.end_order = position
            continue

        normalized_type = _text(row.get("type"))
        base_type = normalized_type.lower().split(maxsplit=1)[0] if normalized_type else "unknown"
        choice_match = SELECT_TYPE.match(normalized_type)
        choice_list = choice_match.group(1).strip() if choice_match else None
        is_note = base_type == "note"
        is_question = _is_question_type(normalized_type)
        stable_id = f"{form_id}:question:{position}:{name or 'row'}"
        question = ParsedQuestion(
            stable_id=stable_id,
            row_order=position,
            excel_row=int(row.get("_row", position + 1)),
            field_name=name or f"row_{position}",
            field_type=normalized_type,
            base_type=base_type,
            choice_list_name=choice_list,
            labels=_language_values(row, "label", default_language),
            hints=_language_values(row, "hint", default_language),
            relevance=_text(row.get("relevance")),
            constraint=_text(row.get("constraint")),
            calculation=_text(row.get("calculation")),
            appearance=_text(row.get("appearance")),
            required=_text(row.get("required")),
            is_question=is_question,
            is_note=is_note,
            source_group_id=stack[-1][0].stable_id if stack else None,
            group_path=[item[0].label for item in stack],
            raw=row,
        )
        parsed.questions.append(question)
        if is_question:
            for group, _ in stack:
                group.question_count += 1
        parsed.dependencies.extend(_dependencies(question))

    final_order = len(survey_rows)
    for group, _ in stack:
        group.end_order = final_order
    return parsed


def _matrix_to_records(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return [{**row, "_row": index + 2} for index, row in enumerate(value)]
    matrix = list(value)
    headers = [_text(item) for item in matrix[0]]
    records: list[dict[str, Any]] = []
    for row_number, cells in enumerate(matrix[1:], start=2):
        record = {"_row": row_number}
        for header, cell in zip(headers, cells):
            if header:
                record[header] = cell
        if any(value not in (None, "") for key, value in record.items() if key != "_row"):
            records.append(record)
    return records


def _language_values(row: dict[str, Any], base: str, default_language: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in row.items():
        if value in (None, ""):
            continue
        normalized = key.lower().replace("::", ":")
        if normalized == base.lower():
            result[default_language] = str(value)
        elif normalized.startswith(f"{base.lower()}:"):
            language = _normalize_language(
                key.replace("::", ":").split(":", 1)[1].strip() or "Translation"
            )
            result[language] = str(value)
    return result


def _dependencies(question: ParsedQuestion) -> list[ParsedDependency]:
    found: list[ParsedDependency] = []
    for column, value in question.raw.items():
        if column.startswith("_") or value in (None, ""):
            continue
        text = str(value)
        patterns = (
            ("field_reference", FIELD_REF),
            ("pulldata_dataset", PULLDATA),
            ("search_dataset", SEARCH),
            ("field_plugin", PLUGIN),
            ("attachment", MEDIA),
        )
        for dependency_type, pattern in patterns:
            for target in pattern.findall(text):
                found.append(
                    ParsedDependency(question.stable_id, dependency_type, str(target), column)
                )
    return found


def _is_question_type(field_type: str) -> bool:
    lowered = field_type.lower().strip()
    if not lowered or lowered in STRUCTURAL_TYPES or lowered == "note":
        return False
    return not lowered.startswith(NON_QUESTION_PREFIXES)


def _best_text(values: dict[str, str], fallback: str) -> str:
    return next(iter(values.values()), fallback)


def _text(value: Any) -> str:
    return "" if value in (None, "") else str(value).strip()


def _normalize_language(value: Any) -> str:
    language = _text(value)
    known = {"english": "English", "arabic": "Arabic", "french": "French"}
    return known.get(language.casefold(), language)
