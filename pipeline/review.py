from __future__ import annotations


ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}


def print_stage_1_table(analysis_payload: dict) -> None:
    print("\nStage 1 risk scores:")
    print("-" * 120)
    print(f"{'Clause':<8} {'Title':<30} {'Category':<24} {'Severity':<10} Summary")
    print("-" * 120)
    for clause in analysis_payload["clauses"]:
        stage_1 = clause["stage_1"]
        print(
            f"{clause['clause_number']:<8} "
            f"{clause['clause_title'][:30]:<30} "
            f"{stage_1['risk_category'][:24]:<24} "
            f"{stage_1['severity']:<10} "
            f"{stage_1['one_sentence_risk_summary']}"
        )
    print("-" * 120)


def collect_operator_overrides(analysis_payload: dict) -> dict:
    print_stage_1_table(analysis_payload)
    overrides: list[dict[str, str]] = []
    valid_clause_numbers = {clause["clause_number"] for clause in analysis_payload["clauses"]}

    while True:
        try:
            response = input(
                "Are there any clauses whose severity you want to override before generating the negotiation brief?\n"
                "Enter clause number and new severity, or press Enter to continue.\n"
            ).strip()
        except EOFError:
            break
        if not response:
            break
        parts = response.replace(",", " ").split()
        if len(parts) != 2:
            print("Invalid input. Use: <clause_number> <severity>")
            continue
        clause_number, new_severity = parts[0], parts[1].lower()
        if clause_number not in valid_clause_numbers:
            print(f"Unknown clause number: {clause_number}")
            continue
        if new_severity not in ALLOWED_SEVERITIES:
            print(f"Invalid severity: {new_severity}")
            continue
        existing = next((item for item in overrides if item["clause_number"] == clause_number), None)
        original_severity = next(
            clause["stage_1"]["severity"]
            for clause in analysis_payload["clauses"]
            if clause["clause_number"] == clause_number
        )
        payload = {
            "clause_number": clause_number,
            "original_severity": original_severity,
            "new_severity": new_severity,
        }
        if existing:
            existing.update(payload)
        else:
            overrides.append(payload)
    return {"overrides": overrides}
