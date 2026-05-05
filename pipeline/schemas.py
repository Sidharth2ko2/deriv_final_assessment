from __future__ import annotations

from typing import Iterable


def _require_keys(item: dict, keys: Iterable[str], context: str) -> None:
    missing = [key for key in keys if key not in item]
    if missing:
        raise ValueError(f"{context} missing keys: {', '.join(missing)}")


def validate_extracted_clauses(clauses: list[dict]) -> None:
    if not isinstance(clauses, list) or not clauses:
        raise ValueError("extracted_clauses.json must contain a non-empty list.")
    for item in clauses:
        _require_keys(
            item,
            ["clause_number", "clause_title", "clause_text", "word_count"],
            "Extracted clause",
        )
        if not isinstance(item["word_count"], int):
            raise ValueError("word_count must be an integer.")


def validate_risk_analysis(
    payload: dict,
    allowed_categories: list[str],
    allowed_severities: list[str],
) -> None:
    _require_keys(payload, ["clauses"], "risk_analysis.json")
    if not isinstance(payload["clauses"], list) or not payload["clauses"]:
        raise ValueError("risk_analysis.json must contain a non-empty 'clauses' list.")
    for item in payload["clauses"]:
        _require_keys(
            item,
            ["clause_number", "clause_title", "stage_1", "final_severity"],
            "Risk analysis clause",
        )
        stage_1 = item["stage_1"]
        _require_keys(
            stage_1,
            [
                "clause_number",
                "risk_category",
                "severity",
                "one_sentence_risk_summary",
                "is_non_standard",
            ],
            "Stage 1 risk result",
        )
        if stage_1["risk_category"] not in allowed_categories:
            raise ValueError(f"Invalid risk category: {stage_1['risk_category']}")
        if stage_1["severity"] not in allowed_severities:
            raise ValueError(f"Invalid severity: {stage_1['severity']}")
        if item["final_severity"] not in allowed_severities:
            raise ValueError(f"Invalid final severity: {item['final_severity']}")
