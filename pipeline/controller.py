from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.briefing import build_fallback_brief
from pipeline.cross_refs import build_cross_references
from pipeline.extraction import extract_clauses
from pipeline.io_utils import load_json, write_json, write_text, read_text
from pipeline.llm_client import LLMClient, DISCLAIMER
from pipeline.redline import build_redlined_contract
from pipeline.review import collect_operator_overrides
from pipeline.scoring import (
    apply_overrides,
    apply_stage_1_results,
    build_stage_1_prompt,
    build_stage_2_prompt,
    build_stage_3_prompt,
    compute_signature_risk_score,
)
from pipeline.schemas import validate_extracted_clauses, validate_risk_analysis
from pipeline.state import PipelineStage, assert_stage_transition


class PipelineController:
    def __init__(
        self,
        root: Path,
        provider: str,
        model: str,
        base_url: str,
        api_key: str | None,
        seed: int,
    ) -> None:
        self.root = root
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.seed = seed
        self.state_path = root / "pipeline_state.json"
        self.manifest_path = root / "run_manifest.json"
        self.llm_calls_path = root / "llm_calls.jsonl"
        self.client = LLMClient(root, provider, model, base_url, api_key, seed)

    def run(self) -> None:
        self._reset_run_artifacts()
        current_stage = PipelineStage.INIT
        self._write_state(current_stage, {"started_at": self._now()})

        current_stage = self._load_inputs(current_stage)
        current_stage = self._extract_clauses(current_stage)
        current_stage = self._score_clauses(current_stage)
        current_stage = self._analyse_critical_clauses(current_stage)
        current_stage = self._operator_review(current_stage)
        current_stage = self._generate_negotiation_brief(current_stage)
        current_stage = self._generate_optional_outputs(current_stage)
        current_stage = self._run_post_generation_validation(current_stage)
        self._finalise(current_stage)

    def _reset_run_artifacts(self) -> None:
        for name in [
            "extracted_clauses.json",
            "risk_analysis.json",
            "operator_overrides.json",
            "negotiation_brief.md",
            "redlined_contract.md",
            "clause_cross_references.json",
            "signature_risk_score.json",
            "llm_calls.jsonl",
            "pipeline_state.json",
            "run_manifest.json",
        ]:
            path = self.root / name
            if path.exists():
                path.unlink()

    def _load_inputs(self, current_stage: PipelineStage) -> PipelineStage:
        next_stage = PipelineStage.INPUTS_LOADED
        assert_stage_transition(current_stage, next_stage)
        contract_path = self.root / "contract.txt"
        framework_path = self.root / "risk_framework.json"
        contract_text = read_text(contract_path)
        framework = load_json(framework_path)
        write_json(
            self.manifest_path,
            {
                "inputs": {
                    "contract.txt": {
                        "path": "contract.txt",
                        "bytes": len(contract_text.encode("utf-8")),
                    },
                    "risk_framework.json": {
                        "path": "risk_framework.json",
                        "bytes": len(json.dumps(framework).encode("utf-8")),
                    },
                },
                "provider": self.provider,
                "model": self.model,
                "seed": self.seed,
                "started_at": self._now(),
            },
        )
        self._write_state(next_stage, {})
        return next_stage

    def _extract_clauses(self, current_stage: PipelineStage) -> PipelineStage:
        next_stage = PipelineStage.CLAUSES_EXTRACTED
        assert_stage_transition(current_stage, next_stage)
        contract_text = read_text(self.root / "contract.txt")
        parsed = extract_clauses(contract_text)
        clause_payload = [
            {
                "clause_number": clause.clause_number,
                "clause_title": clause.clause_title,
                "clause_text": clause.clause_text,
                "word_count": clause.word_count,
            }
            for clause in parsed.clauses
        ]
        validate_extracted_clauses(clause_payload)
        write_json(self.root / "extracted_clauses.json", clause_payload)
        self._write_state(next_stage, {"clause_count": len(clause_payload)})
        return next_stage

    def _score_clauses(self, current_stage: PipelineStage) -> PipelineStage:
        next_stage = PipelineStage.CLAUSES_RISK_SCORED
        assert_stage_transition(current_stage, next_stage)
        clauses = load_json(self.root / "extracted_clauses.json")
        framework = load_json(self.root / "risk_framework.json")
        prompt = build_stage_1_prompt(clauses, framework)
        stage_1_payload = self.client.call_json(
            stage=next_stage.value,
            clause_number=None,
            prompt_payload=prompt,
            input_artifacts=["extracted_clauses.json", "risk_framework.json"],
            output_artifact="risk_analysis.json",
            mock_handler=self._mock_stage_1,
        )
        analysis_payload = apply_stage_1_results(clauses, stage_1_payload, framework)
        validate_risk_analysis(
            analysis_payload,
            allowed_categories=framework["risk_framework"]["categories"],
            allowed_severities=list(framework["risk_framework"]["severity_levels"].keys()),
        )
        write_json(self.root / "risk_analysis.json", analysis_payload)
        self._write_state(next_stage, {})
        return next_stage

    def _analyse_critical_clauses(self, current_stage: PipelineStage) -> PipelineStage:
        next_stage = PipelineStage.CRITICAL_CLAUSES_ANALYSED
        assert_stage_transition(current_stage, next_stage)
        framework = load_json(self.root / "risk_framework.json")
        analysis_payload = load_json(self.root / "risk_analysis.json")
        for clause in analysis_payload["clauses"]:
            if clause["stage_1"]["severity"] != "critical":
                continue
            prompt = build_stage_2_prompt(clause, framework)
            clause["stage_2"] = self.client.call_json(
                stage=next_stage.value,
                clause_number=clause["clause_number"],
                prompt_payload=prompt,
                input_artifacts=["risk_analysis.json", "risk_framework.json"],
                output_artifact="risk_analysis.json",
                mock_handler=self._mock_stage_2,
            )
        write_json(self.root / "risk_analysis.json", analysis_payload)
        self._write_state(next_stage, {})
        return next_stage

    def _operator_review(self, current_stage: PipelineStage) -> PipelineStage:
        next_stage = PipelineStage.OPERATOR_REVIEW_COMPLETE
        assert_stage_transition(current_stage, next_stage)
        analysis_payload = load_json(self.root / "risk_analysis.json")
        overrides_payload = collect_operator_overrides(analysis_payload)
        write_json(self.root / "operator_overrides.json", overrides_payload)
        updated_analysis = apply_overrides(analysis_payload, overrides_payload)
        write_json(self.root / "risk_analysis.json", updated_analysis)
        self._write_state(next_stage, {"override_count": len(overrides_payload["overrides"])})
        return next_stage

    def _generate_negotiation_brief(self, current_stage: PipelineStage) -> PipelineStage:
        next_stage = PipelineStage.NEGOTIATION_BRIEF_GENERATED
        assert_stage_transition(current_stage, next_stage)
        analysis_payload = load_json(self.root / "risk_analysis.json")
        overrides_payload = load_json(self.root / "operator_overrides.json")
        prompt = build_stage_3_prompt(analysis_payload, overrides_payload)
        brief_text = self.client.call_text(
            stage=next_stage.value,
            clause_number=None,
            prompt_payload=prompt,
            input_artifacts=["risk_analysis.json", "operator_overrides.json"],
            output_artifact="negotiation_brief.md",
            mock_handler=lambda payload: build_fallback_brief(analysis_payload),
        )
        required_sections = [
            "## Red Lines",
            "## Priority Negotiations",
            "## Acceptable With Modification",
            "## Standard / Accept",
            "## Opening Position",
        ]
        if not all(s in brief_text for s in required_sections):
            brief_text = build_fallback_brief(analysis_payload)
        if "NOTICE: AI-GENERATED ANALYSIS" not in brief_text:
            disclaimer_lines = DISCLAIMER.splitlines()
            header = f"> **{disclaimer_lines[0]}**\n> {disclaimer_lines[1]}\n\n"
            brief_text = header + brief_text
        write_text(self.root / "negotiation_brief.md", brief_text.strip() + "\n")
        self._write_state(next_stage, {})
        return next_stage

    def _generate_optional_outputs(self, current_stage: PipelineStage) -> PipelineStage:
        next_stage = PipelineStage.OPTIONAL_OUTPUTS_GENERATED
        assert_stage_transition(current_stage, next_stage)
        analysis_payload = load_json(self.root / "risk_analysis.json")
        contract_text = read_text(self.root / "contract.txt")

        write_json(
            self.root / "signature_risk_score.json",
            compute_signature_risk_score(analysis_payload),
        )
        write_json(
            self.root / "clause_cross_references.json",
            build_cross_references(analysis_payload),
        )
        write_text(
            self.root / "redlined_contract.md",
            build_redlined_contract(contract_text, analysis_payload),
        )
        self._write_state(next_stage, {})
        return next_stage

    def _run_post_generation_validation(self, current_stage: PipelineStage) -> PipelineStage:
        next_stage = PipelineStage.VALIDATION_COMPLETE
        assert_stage_transition(current_stage, next_stage)
        analysis_payload = load_json(self.root / "risk_analysis.json")
        framework = load_json(self.root / "risk_framework.json")
        validate_risk_analysis(
            analysis_payload,
            allowed_categories=framework["risk_framework"]["categories"],
            allowed_severities=list(framework["risk_framework"]["severity_levels"].keys()),
        )
        self._write_state(next_stage, {})
        return next_stage

    def _finalise(self, current_stage: PipelineStage) -> None:
        next_stage = PipelineStage.RESULTS_FINALISED
        assert_stage_transition(current_stage, next_stage)
        analysis_payload = load_json(self.root / "risk_analysis.json")
        score_payload = load_json(self.root / "signature_risk_score.json")
        self._write_state(
            next_stage,
            {
                "completed_at": self._now(),
                "final_score": score_payload["final_score"],
                "clause_count": len(analysis_payload["clauses"]),
            },
        )

    def _write_state(self, stage: PipelineStage, metadata: dict[str, Any]) -> None:
        write_json(
            self.state_path,
            {
                "current_stage": stage.value,
                "updated_at": self._now(),
                "metadata": metadata,
            },
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _mock_stage_1(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        clauses = load_json(self.root / "extracted_clauses.json")
        results = []
        for clause in clauses:
            text = clause["clause_text"].lower()
            title = clause["clause_title"].lower()
            category = "financial_exposure"
            severity = "medium"
            summary = "Clause contains terms worth negotiation but not automatically disqualifying."
            non_standard = True

            if "delete all client data" in text or "export their data" in text:
                category = "termination_rights"
                severity = "high"
                summary = "Termination mechanics create material operational and data-retention risk for the client."
            elif "client data" in text or "machine learning models" in text:
                category = "data_rights"
                severity = "critical"
                summary = "Vendor receives expansive ongoing rights over client data, including model training uses."
            elif "aggregate liability" in text or "gross negligence" in text:
                category = "liability_cap"
                severity = "critical"
                summary = "Vendor limits liability so aggressively that serious vendor misconduct may go under-remedied."
            elif "governed by the laws" in text or "arbitration" in text:
                category = "dispute_resolution"
                severity = "medium"
                summary = "Dispute forum and cost allocation are vendor-favourable and may increase enforcement burden."
            elif "modify these terms at any time" in text or "continued use" in text:
                category = "unilateral_modification"
                severity = "critical"
                summary = "Vendor can change core contract terms unilaterally without a negotiated amendment process."
            elif "late payments" in text or "suspend services immediately" in text:
                category = "financial_exposure"
                severity = "high"
                summary = "Payment remedies are unusually aggressive and give the vendor immediate operational leverage."
            elif "customisations" in text or "derivative works" in text or "intellectual property" in title:
                category = "ip_ownership"
                severity = "high"
                summary = "Vendor retains ownership of customer-funded deliverables, limiting the client's long-term control."
            elif "services" in title:
                category = "unilateral_modification"
                severity = "medium"
                summary = "Service scope can be changed or suspended with limited customer protection."
            elif "indemnify" in text:
                category = "financial_exposure"
                severity = "critical"
                summary = "Client indemnity extends to claims tied to vendor negligence, creating significant asymmetric exposure."
            elif "confidentiality" in title:
                category = "data_rights"
                severity = "low"
                summary = "Confidentiality clause is generally standard, though carve-outs still need review."

            results.append(
                {
                    "clause_number": clause["clause_number"],
                    "risk_category": category,
                    "severity": severity,
                    "one_sentence_risk_summary": summary,
                    "is_non_standard": non_standard,
                }
            )
        return {"clauses": results}

    def _mock_stage_2(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        analysis_payload = load_json(self.root / "risk_analysis.json")
        clause_number = self._extract_line_value(prompt_payload["user"], "Clause number:")
        clause = next(item for item in analysis_payload["clauses"] if item["clause_number"] == clause_number)
        category = clause["stage_1"]["risk_category"]
        summary = clause["stage_1"]["one_sentence_risk_summary"]
        return {
            "clause_number": clause_number,
            "harm_mechanism": (
                f"This {category} clause shifts material control or downside to the client because {summary.lower()}"
            ),
            "precedent_framing": (
                "Frame the ask as a request to align the contract with balanced enterprise practice, "
                "preserve continuity, and remove one-sided downside allocation."
            ),
            "redline_suggestions": [
                "Limit the clause to a defined, contract-specific purpose.",
                "Add notice, cure, or mutuality protections that reduce unilateral vendor discretion.",
                "Carve out gross negligence, wilful misconduct, and core client rights from vendor-favourable limitations.",
            ],
            "replacement_clause_text": (
                f"The parties agree that Clause {clause_number} will apply only to the extent reasonably necessary "
                "to perform the Agreement, will not override core client ownership or remedy rights, and will be "
                "subject to prior written notice, commercially reasonable cure rights, and express carve-outs for "
                "gross negligence, wilful misconduct, and unauthorised use of Client Data."
            ),
        }

    def _extract_line_value(self, text: str, prefix: str) -> str:
        for line in text.splitlines():
            if line.startswith(prefix):
                return line.replace(prefix, "", 1).strip()
        raise ValueError(f"Unable to extract value for prefix {prefix}")
