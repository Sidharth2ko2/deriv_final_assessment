from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.io_utils import load_json, load_jsonl, read_text
from pipeline.schemas import validate_extracted_clauses, validate_risk_analysis
from pipeline.state import PipelineStage


REQUIRED_ARTIFACTS = [
    "contract.txt",
    "risk_framework.json",
    "extracted_clauses.json",
    "risk_analysis.json",
    "operator_overrides.json",
    "negotiation_brief.md",
    "llm_calls.jsonl",
    "pipeline_state.json",
]


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"VALIDATION FAILED: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate pipeline outputs.")
    parser.add_argument("--root", default=".", help="Repository root to validate.")
    return parser.parse_args()


def validate_required_files(root: Path) -> None:
    for name in REQUIRED_ARTIFACTS:
        ensure((root / name).exists(), f"Missing required artifact: {name}")


def validate_json_files(root: Path) -> None:
    json_files = [
        "risk_framework.json",
        "extracted_clauses.json",
        "risk_analysis.json",
        "operator_overrides.json",
        "signature_risk_score.json",
        "clause_cross_references.json",
        "pipeline_state.json",
        "run_manifest.json",
    ]
    for name in json_files:
        path = root / name
        if path.exists():
            load_json(path)


def validate_stage_order(root: Path, llm_calls: list[dict]) -> None:
    state_payload = load_json(root / "pipeline_state.json")
    ensure(
        state_payload.get("current_stage") == PipelineStage.RESULTS_FINALISED.value,
        "Pipeline did not reach RESULTS_FINALISED.",
    )
    for call in llm_calls:
        ensure(call["timestamp"], "LLM call record missing timestamp.")
    if llm_calls:
        ensure(
            llm_calls[0]["stage"] == "CLAUSES_RISK_SCORED",
            "The first LLM call must be the single Stage 1 scoring call.",
        )
        ensure(
            llm_calls[-1]["stage"] == "NEGOTIATION_BRIEF_GENERATED",
            "The final required LLM call must generate the negotiation brief.",
        )
        seen_stage_3 = False
        for call in llm_calls:
            if call["stage"] == "NEGOTIATION_BRIEF_GENERATED":
                seen_stage_3 = True
            if call["stage"] == "CRITICAL_CLAUSES_ANALYSED":
                ensure(
                    not seen_stage_3,
                    "Stage 2 critical-clause analysis occurred after negotiation brief generation.",
                )


def validate_inputs_read_from_disk(root: Path) -> None:
    manifest = load_json(root / "run_manifest.json")
    input_artifacts = manifest.get("inputs", {})
    ensure("contract.txt" in input_artifacts, "Run manifest does not reference contract.txt.")
    ensure(
        "risk_framework.json" in input_artifacts,
        "Run manifest does not reference risk_framework.json.",
    )


def validate_scoring(root: Path, llm_calls: list[dict]) -> None:
    framework = load_json(root / "risk_framework.json")["risk_framework"]
    clauses = load_json(root / "extracted_clauses.json")
    validate_extracted_clauses(clauses)
    analysis_payload = load_json(root / "risk_analysis.json")
    validate_risk_analysis(
        analysis_payload,
        allowed_categories=framework["categories"],
        allowed_severities=list(framework["severity_levels"].keys()),
    )

    analysis_items = analysis_payload["clauses"]
    ensure(
        len(analysis_items) == len(clauses),
        "Every extracted clause must have a Stage 1 risk score.",
    )

    clause_numbers = {item["clause_number"] for item in clauses}
    scored_clause_numbers = {item["clause_number"] for item in analysis_items}
    ensure(
        clause_numbers == scored_clause_numbers,
        "Mismatch between extracted clauses and risk analysis clause numbers.",
    )

    stage1_calls = [call for call in llm_calls if call["stage"] == "CLAUSES_RISK_SCORED"]
    ensure(len(stage1_calls) == 1, "Expected exactly one Stage 1 LLM call.")

    critical_clause_numbers = {
        item["clause_number"]
        for item in analysis_items
        if item["stage_1"]["severity"] == "critical"
    }
    stage2_calls = [call for call in llm_calls if call["stage"] == "CRITICAL_CLAUSES_ANALYSED"]
    called_clause_numbers = {call["clause_number"] for call in stage2_calls}
    ensure(
        critical_clause_numbers == called_clause_numbers,
        "Each critical clause must have its own Stage 2 call record.",
    )
    ensure(
        all(call["clause_number"] is not None for call in stage2_calls),
        "Critical clauses must not be batched into a single Stage 2 call.",
    )


def validate_overrides_and_brief(root: Path) -> None:
    overrides_payload = load_json(root / "operator_overrides.json")
    analysis_payload = load_json(root / "risk_analysis.json")
    brief_text = read_text(root / "negotiation_brief.md")

    override_map = {item["clause_number"]: item["new_severity"] for item in overrides_payload["overrides"]}
    final_severities = {
        item["clause_number"]: item["final_severity"]
        for item in analysis_payload["clauses"]
    }
    for clause_number, severity in override_map.items():
        ensure(
            final_severities.get(clause_number) == severity,
            f"Override for clause {clause_number} was not applied downstream.",
        )

    required_sections = [
        "## Red Lines",
        "## Priority Negotiations",
        "## Acceptable With Modification",
        "## Standard / Accept",
        "## Opening Position",
    ]
    for section in required_sections:
        ensure(section in brief_text, f"Negotiation brief missing section: {section}")

    final_buckets = {
        "critical": "## Red Lines",
        "high": "## Priority Negotiations",
        "medium": "## Acceptable With Modification",
        "low": "## Standard / Accept",
    }
    for item in analysis_payload["clauses"]:
        clause_ref = f"Clause {item['clause_number']}"
        ensure(clause_ref in brief_text, f"Negotiation brief missing talking point for {clause_ref}.")
        ensure(
            final_buckets[item["final_severity"]] in brief_text,
            f"Negotiation brief missing target section for {clause_ref}.",
        )


def validate_llm_log_records(root: Path, llm_calls: list[dict]) -> None:
    required_keys = {
        "stage",
        "clause_number",
        "timestamp",
        "provider",
        "model",
        "prompt_hash",
        "input_artifacts",
        "output_artifact",
    }
    for call in llm_calls:
        ensure(required_keys.issubset(call.keys()), "LLM call record missing required fields.")

    ensure(any(call["stage"] == "CLAUSES_RISK_SCORED" for call in llm_calls), "Missing Stage 1 LLM log.")
    ensure(
        any(call["stage"] == "NEGOTIATION_BRIEF_GENERATED" for call in llm_calls),
        "Missing Stage 3 LLM log.",
    )


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    validate_required_files(root)
    validate_json_files(root)
    validate_inputs_read_from_disk(root)
    llm_calls = load_jsonl(root / "llm_calls.jsonl")
    validate_stage_order(root, llm_calls)
    validate_scoring(root, llm_calls)
    validate_overrides_and_brief(root)
    validate_llm_log_records(root, llm_calls)
    print("VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
