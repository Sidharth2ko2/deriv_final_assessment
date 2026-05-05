from __future__ import annotations

from pipeline.llm_client import DISCLAIMER


def build_fallback_brief(analysis_payload: dict) -> str:
    sections = {
        "critical": "## Red Lines",
        "high": "## Priority Negotiations",
        "medium": "## Acceptable With Modification",
        "low": "## Standard / Accept",
    }
    bucketed = {key: [] for key in sections}
    for clause in analysis_payload["clauses"]:
        bucketed[clause["final_severity"]].append(clause)

    disclaimer_lines = DISCLAIMER.splitlines()
    lines = [f"> **{disclaimer_lines[0]}**", f"> {disclaimer_lines[1]}", ""]
    for severity, heading in sections.items():
        lines.append(heading)
        lines.append("")
        if not bucketed[severity]:
            lines.append("No clauses fall into this category after operator review.")
            lines.append("")
            continue
        for clause in bucketed[severity]:
            summary = clause["stage_1"]["one_sentence_risk_summary"]
            lines.append(
                f"- Clause {clause['clause_number']} ({clause['clause_title']}): {summary} "
                f"Final severity: {clause['final_severity']}."
            )
        lines.append("")

    lines.append("## Opening Position")
    lines.append("")
    lines.append(
        "This AI-generated briefing prioritises clauses that create material asymmetry in data use, "
        "liability allocation, operational continuity, and unilateral vendor control. "
        "The negotiation call should start with red-line protections, then move to high-severity "
        "commercial terms that meaningfully shift risk back toward a balanced enterprise position."
    )
    lines.append("")
    return "\n".join(lines)
