from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CategoryMatch:
    topic: str
    subtopic: str
    score: float
    matched_terms: list[str]
    method: str = "rules-v2"


class RuleCategorizer:
    def __init__(self, taxonomy_path: Path) -> None:
        self.taxonomy: dict[str, dict[str, list[str]]] = json.loads(
            taxonomy_path.read_text(encoding="utf-8")
        )

    def classify(self, text: str) -> list[CategoryMatch]:
        normalized_text = _normalize(text)
        matches: list[CategoryMatch] = []
        for topic, subtopics in self.taxonomy.items():
            for subtopic, terms in subtopics.items():
                hits = sorted({term for term in terms if _contains_term(normalized_text, term)})
                if hits:
                    score = min(0.98, 0.55 + 0.12 * len(hits))
                    matches.append(CategoryMatch(topic, subtopic, score, hits))
        return sorted(matches, key=lambda item: (-item.score, item.topic, item.subtopic))

    def taxonomy_rows(self) -> list[tuple[str, str, str]]:
        return [
            (topic, subtopic, term)
            for topic, subtopics in self.taxonomy.items()
            for subtopic, terms in subtopics.items()
            for term in terms
        ]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold().replace("_", " ").replace("-", " ")).strip()


def _contains_term(normalized_text: str, term: str) -> bool:
    normalized_term = _normalize(term)
    if " " not in normalized_term and len(normalized_term) <= 3:
        return bool(re.search(rf"(?<!\w){re.escape(normalized_term)}(?!\w)", normalized_text))
    return normalized_term in normalized_text
