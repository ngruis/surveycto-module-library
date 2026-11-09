from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .categorization import RuleCategorizer
from .config import Settings
from .credentials import Credentials
from .database import initialize, replace_form, transaction
from .modules import infer_modules
from .parsing import ParsedDefinition, parse_definition
from .retrieval import (
    ProgressCallback,
    RetrievedDefinition,
    SurveyCTOApiRetriever,
    load_raw_definition,
)

PROCESSING_VERSION = "2026-09-08.4"


@dataclass
class ValidationSummary:
    run_id: str
    forms_found: int = 0
    forms_downloaded: int = 0
    forms_reused: int = 0
    failed_downloads: int = 0
    parsed_forms: int = 0
    total_survey_rows: int = 0
    total_questions: int = 0
    total_choices: int = 0
    source_groups: int = 0
    inferred_modules: int = 0
    categorized_questions: int = 0
    uncategorized_questions: int = 0
    dependencies_detected: int = 0
    classification_failures: int = 0
    unchanged_forms: int = 0
    duration_seconds: float = 0.0
    failures: list[dict[str, str]] | None = None


def run_update(
    settings: Settings,
    credentials: Credentials,
    limit: int | None = None,
    reuse_existing: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> ValidationSummary:
    started_monotonic = time.monotonic()
    run_id = _run_id()
    timestamp = _utc_now()
    summary = ValidationSummary(run_id=run_id, failures=[])
    logger = _logger(settings, run_id)
    definitions: list[RetrievedDefinition] = []
    initialize(settings.database_path)
    _start_run(settings, run_id, timestamp)
    try:
        retriever = SurveyCTOApiRetriever(settings.server, credentials)
        form_ids = retriever.list_form_ids()
        if limit is not None:
            form_ids = form_ids[:limit]
        summary.forms_found = len(form_ids)
        definitions, failures = retriever.retrieve_all(
            settings.raw_directory,
            run_id,
            form_ids=form_ids,
            reuse_existing=reuse_existing,
            progress_callback=progress_callback,
        )
        summary.forms_downloaded = sum(
            definition.retrieval_status == "downloaded" for definition in definitions
        )
        summary.forms_reused = sum(
            definition.retrieval_status == "reused" for definition in definitions
        )
        summary.failed_downloads = len(failures)
        summary.failures.extend(
            {"form_id": form_id, "stage": "download", "error": error} for form_id, error in failures
        )
        _process_definitions(settings, definitions, summary, timestamp, logger)
        status = "success" if not failures else "partial"
        summary.duration_seconds = round(time.monotonic() - started_monotonic, 2)
        finished_at = _utc_now()
        _finish_run(settings, summary, status, finished_at)
        _write_validation(settings, summary)
        _write_run_metadata(
            settings, summary, definitions, timestamp, finished_at, status
        )
        return summary
    except Exception as exc:
        logger.exception("Update failed")
        summary.failures.append({"form_id": "", "stage": "run", "error": str(exc)})
        summary.duration_seconds = round(time.monotonic() - started_monotonic, 2)
        finished_at = _utc_now()
        _finish_run(settings, summary, "failed", finished_at)
        _write_validation(settings, summary)
        if (settings.raw_directory / run_id).exists():
            _write_run_metadata(
                settings, summary, definitions, timestamp, finished_at, "failed"
            )
        raise


def process_raw_files(settings: Settings, paths: Iterable[Path]) -> ValidationSummary:
    run_id = _run_id("import")
    timestamp = _utc_now()
    summary = ValidationSummary(run_id=run_id, failures=[])
    definitions = [load_raw_definition(path) for path in paths]
    summary.forms_found = summary.forms_downloaded = len(definitions)
    initialize(settings.database_path)
    _start_run(settings, run_id, timestamp)
    _process_definitions(settings, definitions, summary, timestamp, _logger(settings, run_id))
    _finish_run(settings, summary, "success", timestamp)
    _write_validation(settings, summary)
    return summary


def _process_definitions(
    settings: Settings,
    definitions: list[RetrievedDefinition],
    summary: ValidationSummary,
    timestamp: str,
    logger: logging.Logger,
) -> None:
    categorizer = RuleCategorizer(settings.taxonomy_path)
    with transaction(settings.database_path) as connection:
        classification_id = f"classify_{summary.run_id}"
        connection.execute(
            """INSERT OR REPLACE INTO classification_runs
            (id,scrape_run_id,started_at,provider,model,status) VALUES (?,?,?,?,?,?)""",
            (classification_id, summary.run_id, timestamp, "rules", "taxonomy-v2", "running"),
        )
        connection.executemany(
            "INSERT OR IGNORE INTO taxonomy_terms(topic,subtopic,term) VALUES (?,?,?)",
            categorizer.taxonomy_rows(),
        )
        for retrieved in definitions:
            try:
                parsed = parse_definition(retrieved.payload, retrieved.form_id)
                existing = connection.execute(
                    "SELECT content_hash, processing_version FROM forms WHERE form_id = ?",
                    (parsed.form_id,),
                ).fetchone()
                if (
                    existing
                    and existing["content_hash"] == retrieved.content_hash
                    and existing["processing_version"] == PROCESSING_VERSION
                ):
                    summary.unchanged_forms += 1
                    connection.execute(
                        "UPDATE forms SET last_seen_run_id = ?, updated_at = ? WHERE form_id = ?",
                        (summary.run_id, timestamp, parsed.form_id),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO raw_form_definitions(form_id,scrape_run_id,content_hash,raw_path,retrieved_at) VALUES (?,?,?,?,?)",
                        (
                            parsed.form_id,
                            summary.run_id,
                            retrieved.content_hash,
                            str(_portable_path(retrieved.raw_path, settings.storage_root)),
                            timestamp,
                        ),
                    )
                    continue
                modules = infer_modules(parsed)
                question_matches = {
                    question.stable_id: categorizer.classify(_question_text(question))
                    for question in parsed.questions
                    if question.is_question
                }
                module_matches = {
                    module.stable_id: categorizer.classify(
                        " ".join(
                            [
                                module.label,
                                *[
                                    _question_text_by_id(parsed, item)
                                    for item in module.question_ids
                                ],
                            ]
                        )
                    )
                    for module in modules
                }
                replace_form(
                    connection,
                    parsed,
                    modules,
                    question_matches,
                    module_matches,
                    server=settings.server,
                    run_id=summary.run_id,
                    content_hash=retrieved.content_hash,
                    raw_path=_portable_path(retrieved.raw_path, settings.root),
                    timestamp=timestamp,
                    processing_version=PROCESSING_VERSION,
                )
                _tally(summary, parsed, modules, question_matches)
            except Exception as exc:
                logger.exception("Failed to parse %s", retrieved.form_id)
                summary.failures.append(
                    {"form_id": retrieved.form_id, "stage": "parse", "error": str(exc)}
                )
        connection.execute(
            """UPDATE classification_runs SET finished_at=?,status=?,items_classified=?,failures=?
            WHERE id=?""",
            (
                _utc_now(),
                "success" if not summary.classification_failures else "partial",
                summary.categorized_questions,
                summary.classification_failures,
                classification_id,
            ),
        )


def _question_text(question) -> str:
    return " ".join([question.field_name, *question.labels.values(), *question.hints.values()])


def _portable_path(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def _question_text_by_id(parsed: ParsedDefinition, stable_id: str) -> str:
    return next((_question_text(q) for q in parsed.questions if q.stable_id == stable_id), "")


def _tally(summary, parsed, modules, question_matches) -> None:
    summary.parsed_forms += 1
    summary.total_survey_rows += len(parsed.questions) + len(parsed.groups) * 2
    summary.total_questions += sum(q.is_question for q in parsed.questions)
    summary.total_choices += len(parsed.choices)
    summary.source_groups += len(parsed.groups)
    summary.inferred_modules += len(modules)
    categorized = sum(bool(matches) for matches in question_matches.values())
    summary.categorized_questions += categorized
    summary.uncategorized_questions += len(question_matches) - categorized
    summary.dependencies_detected += len(parsed.dependencies)


def _start_run(settings: Settings, run_id: str, timestamp: str) -> None:
    with transaction(settings.database_path) as connection:
        connection.execute(
            "INSERT INTO scrape_runs(id,started_at,status) VALUES (?,?,?)",
            (run_id, timestamp, "running"),
        )


def _finish_run(
    settings: Settings, summary: ValidationSummary, status: str, timestamp: str
) -> None:
    with transaction(settings.database_path) as connection:
        connection.execute(
            """UPDATE scrape_runs SET finished_at=?,status=?,forms_found=?,forms_downloaded=?,forms_reused=?,forms_failed=?,
            forms_parsed=?,questions=?,choices=?,source_groups=?,inferred_modules=?,categorized_questions=?,
            uncategorized_questions=?,dependencies=?,error_summary=? WHERE id=?""",
            (
                timestamp,
                status,
                summary.forms_found,
                summary.forms_downloaded,
                summary.forms_reused,
                summary.failed_downloads,
                summary.parsed_forms,
                summary.total_questions,
                summary.total_choices,
                summary.source_groups,
                summary.inferred_modules,
                summary.categorized_questions,
                summary.uncategorized_questions,
                summary.dependencies_detected,
                json.dumps(summary.failures, ensure_ascii=False),
                summary.run_id,
            ),
        )


def _write_validation(settings: Settings, summary: ValidationSummary) -> Path:
    settings.log_directory.mkdir(parents=True, exist_ok=True)
    path = settings.log_directory / f"validation_{summary.run_id}.json"
    path.write_text(json.dumps(asdict(summary), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_run_metadata(
    settings: Settings,
    summary: ValidationSummary,
    definitions: list[RetrievedDefinition],
    started_at: str,
    finished_at: str,
    status: str,
) -> Path:
    """Write the retrieval roster and processing output beside each run's JSON files."""
    run_dir = settings.raw_directory / summary.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    definition_rows = []
    for definition in sorted(definitions, key=lambda item: item.form_id):
        try:
            raw_path = definition.raw_path.relative_to(settings.raw_directory)
        except ValueError:
            raw_path = definition.raw_path
        definition_rows.append(
            {
                "form_id": definition.form_id,
                "retrieval_status": definition.retrieval_status,
                "sha256": definition.content_hash,
                "raw_path": str(raw_path),
            }
        )

    metadata = {
        "run_id": summary.run_id,
        "server": settings.server,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "processing_version": PROCESSING_VERSION,
        "retrieval": {
            "forms_found": summary.forms_found,
            "forms_downloaded": summary.forms_downloaded,
            "forms_reused": summary.forms_reused,
            "failed_downloads": summary.failed_downloads,
            "downloaded_form_ids": [
                item.form_id for item in definitions if item.retrieval_status == "downloaded"
            ],
            "reused_form_ids": [
                item.form_id for item in definitions if item.retrieval_status == "reused"
            ],
        },
        "processing": {
            "parsed_forms": summary.parsed_forms,
            "unchanged_forms": summary.unchanged_forms,
            "total_survey_rows": summary.total_survey_rows,
            "total_questions": summary.total_questions,
            "total_choices": summary.total_choices,
            "source_groups": summary.source_groups,
            "inferred_modules": summary.inferred_modules,
            "categorized_questions": summary.categorized_questions,
            "uncategorized_questions": summary.uncategorized_questions,
            "dependencies_detected": summary.dependencies_detected,
            "classification_failures": summary.classification_failures,
            "duration_seconds": summary.duration_seconds,
        },
        "failures": summary.failures,
        "definitions": definition_rows,
        "validation_summary": asdict(summary),
    }
    path = run_dir / "run_metadata.json"
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _logger(settings: Settings, run_id: str) -> logging.Logger:
    settings.log_directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"surveycto_module_library.{run_id}")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(
            settings.log_directory / f"update_{run_id}.log", encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def _run_id(prefix: str = "run") -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
