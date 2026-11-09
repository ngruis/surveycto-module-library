from __future__ import annotations

import re
from dataclasses import dataclass

from .parsing import ParsedDefinition, ParsedGroup, ParsedQuestion

NOISE_TERMS = (
    "consent",
    "assent",
    "admin",
    "administrative",
    "enumerator",
    "survey metadata",
    "quality control",
    "back check",
    "eligibility",
    "introduction",
    "location details",
    "audio audit",
    "test section",
    "موافقة",
    "بمعرفة الباحث",
    "للباحث",
    "بيانات الباحث",
    "اسم الباحث",
    "ملاحظات الباحث",
    "للمشرف",
)


@dataclass(frozen=True)
class InferredModule:
    stable_id: str
    name: str
    label: str
    source_group_id: str | None
    start_order: int
    end_order: int
    question_ids: list[str]
    inference_method: str
    confidence: float
    is_noise: bool


def infer_modules(parsed: ParsedDefinition, min_questions: int = 2) -> list[InferredModule]:
    modules: list[InferredModule] = []
    assigned: set[str] = set()
    substantive_groups = sorted(
        (group for group in parsed.groups if group.question_count >= min_questions),
        key=lambda group: (-group.depth, group.start_order),
    )
    for group in substantive_groups:
        questions = [
            question
            for question in parsed.questions
            if question.is_question
            and group.start_order < question.row_order < group.end_order
            and question.stable_id not in assigned
        ]
        if len(questions) < min_questions:
            continue
        label = group.label or _humanize(group.name)
        module = _from_group(parsed, group, label, questions)
        modules.append(module)
        assigned.update(module.question_ids)

    loose_questions = [q for q in parsed.questions if q.is_question and q.stable_id not in assigned]
    for run in _loose_runs(loose_questions):
        for index in range(0, len(run), 8):
            chunk = run[index : index + 8]
            if len(chunk) < min_questions:
                continue
            label = _loose_label(parsed, chunk, len(modules) + 1)
            modules.append(
                InferredModule(
                    stable_id=f"{parsed.form_id}:module:loose:{chunk[0].row_order}",
                    name=f"loose_{chunk[0].row_order}",
                    label=label,
                    source_group_id=None,
                    start_order=chunk[0].row_order,
                    end_order=chunk[-1].row_order,
                    question_ids=[q.stable_id for q in chunk],
                    inference_method="proximity-v1",
                    confidence=0.45,
                    is_noise=_is_noise(label, chunk),
                )
            )
    return sorted(modules, key=lambda module: module.start_order)


def _loose_runs(questions: list[ParsedQuestion]) -> list[list[ParsedQuestion]]:
    runs: list[list[ParsedQuestion]] = []
    for question in questions:
        if not runs or question.row_order - runs[-1][-1].row_order > 3:
            runs.append([question])
        else:
            runs[-1].append(question)
    return runs


def _from_group(
    parsed: ParsedDefinition, group: ParsedGroup, label: str, questions: list[ParsedQuestion]
) -> InferredModule:
    return InferredModule(
        stable_id=f"{parsed.form_id}:module:{group.start_order}:{group.name}",
        name=group.name,
        label=label,
        source_group_id=group.stable_id,
        start_order=group.start_order,
        end_order=group.end_order,
        question_ids=[question.stable_id for question in questions],
        inference_method="source-group-v1",
        confidence=0.85 if group.label else 0.68,
        is_noise=_is_noise(label, questions),
    )


def _is_noise(label: str, questions: list[ParsedQuestion]) -> bool:
    text = " ".join([label, *(q.field_name for q in questions)]).casefold()
    return any(term in text for term in NOISE_TERMS)


def _loose_label(parsed: ParsedDefinition, questions: list[ParsedQuestion], number: int) -> str:
    preceding_notes = [
        q
        for q in parsed.questions
        if q.is_note
        and q.row_order < questions[0].row_order
        and q.row_order >= questions[0].row_order - 3
    ]
    if preceding_notes:
        labels = preceding_notes[-1].labels
        if labels:
            return _clean_label(next(iter(labels.values())))[:120]
    return f"Questions {questions[0].row_order}-{questions[-1].row_order}"


def _clean_label(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value).strip()


def _humanize(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("_", " ").replace("-", " ")).strip().title()
