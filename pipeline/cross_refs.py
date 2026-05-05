from __future__ import annotations

from itertools import combinations


COMPOUND_PATTERNS = [
    ("data_rights", "termination_rights", "Data retention and deletion rights combine to increase loss-of-control risk."),
    ("unilateral_modification", "financial_exposure", "Vendor amendment power compounds payment and suspension leverage."),
    ("liability_cap", "financial_exposure", "Aggressive payment remedies combined with low vendor liability concentrate downside on the client."),
]


def build_cross_references(analysis_payload: dict) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    clauses = analysis_payload["clauses"]
    for clause_a, clause_b in combinations(clauses, 2):
        category_a = clause_a["stage_1"]["risk_category"]
        category_b = clause_b["stage_1"]["risk_category"]
        severity_pair = {clause_a["final_severity"], clause_b["final_severity"]}
        for first, second, description in COMPOUND_PATTERNS:
            if {category_a, category_b} == {first, second}:
                combined_severity = "critical" if "critical" in severity_pair else "high"
                results.append(
                    {
                        "clause_a": clause_a["clause_number"],
                        "clause_b": clause_b["clause_number"],
                        "combined_risk_description": description,
                        "combined_severity": combined_severity,
                    }
                )
                break
    return results
