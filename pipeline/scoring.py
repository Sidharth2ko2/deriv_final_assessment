from __future__ import annotations

from typing import Any

from pipeline.llm_client import DISCLAIMER


SEVERITY_POINTS = {
    "critical": 25,
    "high": 12,
    "medium": 5,
    "low": 1,
}


def build_stage_1_prompt(clauses: list[dict], framework: dict) -> dict[str, str]:
    categories = framework["risk_framework"]["categories"]
    severities = framework["risk_framework"]["severity_levels"]
    return {
        "system": (
            "You are a lead systems engineer preparing structured AI-generated contract risk analysis. "
            "Return JSON only. Do not add commentary. "
            "Use exactly one allowed category and one allowed severity for each clause. "
            "Do not invent categories or severities. This output is not legal advice."
        ),
        "user": (
            "Classify every clause in the contract using the exact framework below.\n\n"
            f"Allowed categories: {categories}\n"
            f"Allowed severity levels: {severities}\n\n"
            "Return this JSON shape:\n"
            '{"clauses":[{"clause_number":"string","risk_category":"string","severity":"string",'
            '"one_sentence_risk_summary":"string","is_non_standard":true}]}\n\n'
            f"Clauses:\n{clauses}\n\nFramework:\n{framework}"
        ),
    }


def build_stage_2_prompt(clause: dict, framework: dict) -> dict[str, str]:
    severity = clause["stage_1"]["severity"]
    severity_definition = framework["risk_framework"]["severity_levels"][severity]
    return {
        "system": (
            "You are generating deeper AI-assisted negotiation analysis for one critical contract clause. "
            "Return JSON only. This is not legal advice."
        ),
        "user": (
            "Analyze this clause and return JSON with the following shape:\n"
            '{"clause_number":"string","harm_mechanism":"string","precedent_framing":"string",'
            '"redline_suggestions":["string","string","string"],'
            '"replacement_clause_text":"string"}\n\n'
            f"Clause number: {clause['clause_number']}\n"
            f"Clause title: {clause['clause_title']}\n"
            f"Risk category: {clause['stage_1']['risk_category']}\n"
            f"Severity definition: {severity_definition}\n"
            f"One sentence risk summary: {clause['stage_1']['one_sentence_risk_summary']}\n"
            f"Clause text:\n{clause['clause_text']}\n"
        ),
    }


def build_stage_3_prompt(analysis_payload: dict, overrides_payload: dict) -> dict[str, str]:
    return {
        "system": (
            "You are generating an AI-assisted negotiation brief from structured contract risk outputs. "
            "Return Markdown only. Do not present the result as legal advice."
        ),
        "user": (
            f"Start the document with this exact disclaimer block, preserving every character:\n"
            f"> **{DISCLAIMER.splitlines()[0]}**\n"
            f"> {DISCLAIMER.splitlines()[1]}\n\n"
            "Then generate the rest of negotiation_brief.md with exactly these sections in this order:\n"
            "## Red Lines\n"
            "## Priority Negotiations\n"
            "## Acceptable With Modification\n"
            "## Standard / Accept\n"
            "## Opening Position\n\n"
            "Each non-empty severity section must contain clause-specific talking points referencing "
            "the clause number (e.g. 'Clause 3'). "
            "Use final post-override severities. Opening Position must be 2-3 sentences.\n\n"
            f"Risk analysis:\n{analysis_payload}\n\n"
            f"Operator overrides:\n{overrides_payload}\n"
        ),
    }


def apply_stage_1_results(
    clauses: list[dict],
    stage_1_payload: dict[str, Any],
    framework: dict,
) -> dict[str, Any]:
    allowed_categories = set(framework["risk_framework"]["categories"])
    allowed_severities = set(framework["risk_framework"]["severity_levels"].keys())
    stage_1_by_clause = {
        item["clause_number"]: item
        for item in stage_1_payload["clauses"]
    }
    analysis_items: list[dict[str, Any]] = []
    for clause in clauses:
        clause_number = clause["clause_number"]
        if clause_number not in stage_1_by_clause:
            raise ValueError(f"Missing Stage 1 output for clause {clause_number}")
        stage_1 = stage_1_by_clause[clause_number]
        if stage_1["risk_category"] not in allowed_categories:
            raise ValueError(f"Invalid risk category for clause {clause_number}")
        if stage_1["severity"] not in allowed_severities:
            raise ValueError(f"Invalid severity for clause {clause_number}")
        analysis_items.append(
            {
                "clause_number": clause_number,
                "clause_title": clause["clause_title"],
                "clause_text": clause["clause_text"],
                "word_count": clause["word_count"],
                "stage_1": stage_1,
                "stage_2": None,
                "market_standard_comparison": build_market_standard_comparison(stage_1),
                "final_severity": stage_1["severity"],
            }
        )
    return {"clauses": analysis_items}


def apply_overrides(analysis_payload: dict, overrides_payload: dict) -> dict:
    override_map = {item["clause_number"]: item["new_severity"] for item in overrides_payload["overrides"]}
    for clause in analysis_payload["clauses"]:
        clause["final_severity"] = override_map.get(
            clause["clause_number"],
            clause["stage_1"]["severity"],
        )
    return analysis_payload


def build_market_standard_comparison(stage_1: dict) -> dict[str, str]:
    severity = stage_1["severity"]
    summary = stage_1["one_sentence_risk_summary"]
    if severity in {"critical", "high"}:
        comparison = (
            "General AI-generated comparison: this clause appears more vendor-favourable than a "
            f"balanced enterprise position because {summary.lower()}"
        )
    else:
        comparison = (
            "General AI-generated comparison: this clause is closer to market-standard vendor paper, "
            f"though it still warrants review because {summary.lower()}"
        )
    return {
        "market_standard_comparison": comparison,
        "basis": "LLM general knowledge, not a sourced legal database",
    }


def compute_signature_risk_score(analysis_payload: dict) -> dict[str, Any]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for clause in analysis_payload["clauses"]:
        counts[clause["final_severity"]] += 1
    raw_score = sum(SEVERITY_POINTS[level] * count for level, count in counts.items())
    final_score = min(100, raw_score)
    justification = (
        "The sign-as-is score is a deterministic weighted sum of final post-override severities. "
        f"The current distribution is {counts['critical']} critical, {counts['high']} high, "
        f"{counts['medium']} medium, and {counts['low']} low clauses, which produces a capped "
        f"risk score of {final_score}/100."
    )
    return {
        "formula": "score = min(100, critical*25 + high*12 + medium*5 + low*1)",
        "severity_distribution": counts,
        "final_score": final_score,
        "justification": justification,
    }
