from __future__ import annotations

from enum import Enum


class PipelineStage(str, Enum):
    INIT = "INIT"
    INPUTS_LOADED = "INPUTS_LOADED"
    CLAUSES_EXTRACTED = "CLAUSES_EXTRACTED"
    CLAUSES_RISK_SCORED = "CLAUSES_RISK_SCORED"
    CRITICAL_CLAUSES_ANALYSED = "CRITICAL_CLAUSES_ANALYSED"
    OPERATOR_REVIEW_COMPLETE = "OPERATOR_REVIEW_COMPLETE"
    NEGOTIATION_BRIEF_GENERATED = "NEGOTIATION_BRIEF_GENERATED"
    OPTIONAL_OUTPUTS_GENERATED = "OPTIONAL_OUTPUTS_GENERATED"
    VALIDATION_COMPLETE = "VALIDATION_COMPLETE"
    RESULTS_FINALISED = "RESULTS_FINALISED"


STAGE_ORDER = [
    PipelineStage.INIT,
    PipelineStage.INPUTS_LOADED,
    PipelineStage.CLAUSES_EXTRACTED,
    PipelineStage.CLAUSES_RISK_SCORED,
    PipelineStage.CRITICAL_CLAUSES_ANALYSED,
    PipelineStage.OPERATOR_REVIEW_COMPLETE,
    PipelineStage.NEGOTIATION_BRIEF_GENERATED,
    PipelineStage.OPTIONAL_OUTPUTS_GENERATED,
    PipelineStage.VALIDATION_COMPLETE,
    PipelineStage.RESULTS_FINALISED,
]


def assert_stage_transition(current_stage: PipelineStage, next_stage: PipelineStage) -> None:
    current_index = STAGE_ORDER.index(current_stage)
    next_index = STAGE_ORDER.index(next_stage)
    if next_index != current_index + 1:
        raise ValueError(
            f"Invalid stage transition from {current_stage.value} to {next_stage.value}."
        )
