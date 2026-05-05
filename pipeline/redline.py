from __future__ import annotations

from pipeline.extraction import extract_clauses
from pipeline.llm_client import DISCLAIMER


def build_redlined_contract(contract_text: str, analysis_payload: dict) -> str:
    parsed = extract_clauses(contract_text)
    replacement_map = {}
    for clause in analysis_payload["clauses"]:
        stage_2 = clause.get("stage_2")
        if stage_2 and stage_2.get("replacement_clause_text"):
            replacement_map[clause["clause_number"]] = stage_2["replacement_clause_text"].strip()

    disclaimer_lines = DISCLAIMER.splitlines()
    lines = [f"> **{disclaimer_lines[0]}**", f"> {disclaimer_lines[1]}", ""]
    if parsed.preamble:
        lines.append(parsed.preamble)
        lines.append("")

    for clause in parsed.clauses:
        lines.append(f"{clause.clause_number}. {clause.clause_title}")
        lines.append("")
        if clause.clause_number in replacement_map:
            bolded = f"**{replacement_map[clause.clause_number]}**"
            lines.append(bolded)
        else:
            lines.append(clause.clause_text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"
