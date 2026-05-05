# deriv_final_assessment

Replayable contract-risk pipeline for the Deriv AI Engineer assessment. The implementation ingests `contract.txt` and `risk_framework.json`, deterministically extracts clauses, runs staged LLM-backed risk analysis, pauses for operator overrides, and produces a negotiation brief plus audit artifacts.

## Objective

Build a production-style, replayable pipeline that:

- extracts numbered clauses deterministically before any LLM call,
- scores every clause against the provided risk framework,
- deep-analyzes only Stage 1 critical clauses with one call per clause,
- enforces an operator review checkpoint before briefing generation,
- preserves intermediate artifacts and LLM call logs,
- generates AI-assisted negotiation outputs while clearly disclaiming legal advice.

## Execution

Primary run command:

```bash
python main.py run
```

Validation command:

```bash
python validate.py
```

The pipeline now defaults to local Ollama with `llama3.1:8b`. Start Ollama and pull the model first:

```bash
ollama pull llama3.1:8b
python main.py run
```

If you want a deterministic local smoke test with no model dependency:

```bash
python main.py run --provider mock --model heuristic-v1
```

If you want a remote OpenAI-compatible endpoint instead:

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your_key
export LLM_MODEL=gpt-4.1-mini
python main.py run
```

You can also point the default local path at a non-default Ollama endpoint:

```bash
export LLM_BASE_URL=http://localhost:11434/v1
export LLM_MODEL=llama3.1:8b
python main.py run
```

## Stage Machine

The controller enforces this exact sequence:

```text
INIT
-> INPUTS_LOADED
-> CLAUSES_EXTRACTED
-> CLAUSES_RISK_SCORED
-> CRITICAL_CLAUSES_ANALYSED
-> OPERATOR_REVIEW_COMPLETE
-> NEGOTIATION_BRIEF_GENERATED
-> OPTIONAL_OUTPUTS_GENERATED
-> VALIDATION_COMPLETE
-> RESULTS_FINALISED
```

## Produced Artifacts

Required artifacts:

- `contract.txt`
- `risk_framework.json`
- `extracted_clauses.json`
- `risk_analysis.json`
- `operator_overrides.json`
- `negotiation_brief.md`
- `llm_calls.jsonl`

Attempted optional artifacts:

- `redlined_contract.md`
- `clause_cross_references.json`
- `signature_risk_score.json`

Supporting internal artifacts:

- `pipeline_state.json`
- `run_manifest.json`

## Implementation Notes

- Clause extraction is deterministic regex-based code in [pipeline/extraction.py](/Users/sidhu/Desktop/Deriv_final_assessment/pipeline/extraction.py:1).
- LLM calls are logged one-per-line in `llm_calls.jsonl` with stage, clause number, provider, model, prompt hash, and artifact references.
- Local Ollama runs use the OpenAI-compatible `v1/chat/completions` endpoint with a fixed seed for better replayability.
- Stage 1 scoring is one call for all clauses.
- Stage 2 deep analysis is one separate call for each critical clause.
- Operator overrides are persisted and applied to downstream final severities.
- Markdown outputs are explicitly marked as AI-generated analysis and not legal advice.
