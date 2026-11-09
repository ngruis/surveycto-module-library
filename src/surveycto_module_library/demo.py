from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .retrieval import RetrievedDefinition


def demo_definitions(raw_root: Path, run_id: str) -> list[RetrievedDefinition]:
    payloads = [_education_form(), _wellbeing_form()]
    run_dir = raw_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    definitions: list[RetrievedDefinition] = []
    for payload in payloads:
        form_id = payload["formId"]
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        path = run_dir / f"{form_id}__{digest[:12]}.json"
        envelope = {
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "server": "demo",
            "form_id": form_id,
            "sha256": digest,
            "definition": payload,
        }
        path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
        definitions.append(RetrievedDefinition(form_id, payload, digest, path))
    return definitions


def _education_form() -> dict:
    survey = [
        [
            "type",
            "name",
            "label",
            "label:Arabic",
            "relevance",
            "constraint",
            "required",
            "appearance",
        ],
        [
            "begin group",
            "schooling",
            "School enrollment and attendance",
            "الالتحاق بالمدرسة والحضور",
            "",
            "",
            "",
            "organized",
        ],
        [
            "select_one yesno",
            "enrolled",
            "Are you currently enrolled in school?",
            "هل أنت ملتحق بالمدرسة حاليا؟",
            "",
            "",
            "yes",
            "",
        ],
        [
            "integer",
            "days_absent",
            "How many school days did you miss last month?",
            "كم يوما دراسيا تغيبت الشهر الماضي؟",
            "${enrolled} = 'yes'",
            ". >= 0 and . <= 31",
            "yes",
            "",
        ],
        [
            "select_one grade",
            "highest_grade",
            "What is the highest grade you completed?",
            "ما أعلى صف أكملته؟",
            "",
            "",
            "yes",
            "minimal",
        ],
        ["end group", "schooling", "", "", "", "", "", ""],
        [
            "begin group",
            "employment",
            "Employment and earnings",
            "العمل والدخل",
            "",
            "",
            "",
            "organized",
        ],
        [
            "select_one yesno",
            "worked",
            "Did you work for pay in the last seven days?",
            "هل عملت مقابل أجر خلال الأيام السبعة الماضية؟",
            "",
            "",
            "yes",
            "",
        ],
        [
            "decimal",
            "earnings",
            "What were your total earnings?",
            "ما إجمالي دخلك؟",
            "${worked} = 'yes'",
            ". >= 0",
            "yes",
            "",
        ],
        ["end group", "employment", "", "", "", "", "", ""],
    ]
    choices = [
        ["list_name", "value", "label", "label:Arabic"],
        ["yesno", "yes", "Yes", "نعم"],
        ["yesno", "no", "No", "لا"],
        ["grade", "1", "Primary", "ابتدائي"],
        ["grade", "2", "Secondary", "ثانوي"],
    ]
    settings = [
        ["form_title", "form_id", "version", "default_language"],
        ["Youth Education Survey", "demo_education", "2026090801", "English"],
    ]
    return {
        "formId": "demo_education",
        "fieldsRowsAndColumns": survey,
        "choicesRowsAndColumns": choices,
        "settingsRowsAndColumns": settings,
    }


def _wellbeing_form() -> dict:
    survey = [
        ["type", "name", "label", "relevance", "required"],
        ["begin group", "mh", "Mental health and wellbeing", "", ""],
        [
            "select_one frequency",
            "little_interest",
            "Over the last two weeks, how often have you had little interest or pleasure in doing things?",
            "",
            "yes",
        ],
        [
            "select_one frequency",
            "feeling_down",
            "How often have you felt down, depressed, or hopeless?",
            "",
            "yes",
        ],
        [
            "integer",
            "stress_scale",
            "On a scale from 0 to 10, how stressed do you feel today?",
            "",
            "yes",
        ],
        ["end group", "mh", "", "", ""],
        ["begin group", "admin", "Enumerator and administrative checks", "", ""],
        ["text", "enumerator_comment", "Enumerator comment", "", ""],
        ["text", "backcheck_flag", "Back check status", "", ""],
        ["end group", "admin", "", "", ""],
    ]
    choices = [
        ["list_name", "value", "label"],
        ["frequency", "0", "Not at all"],
        ["frequency", "1", "Several days"],
        ["frequency", "2", "More than half the days"],
        ["frequency", "3", "Nearly every day"],
    ]
    settings = [
        ["form_title", "form_id", "version", "default_language"],
        ["Wellbeing Follow-up", "demo_wellbeing", "2026090801", "English"],
    ]
    return {
        "formId": "demo_wellbeing",
        "fieldsRowsAndColumns": survey,
        "choicesRowsAndColumns": choices,
        "settingsRowsAndColumns": settings,
    }
