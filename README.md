# Deriv AI Engineer Assessment — Contract Risk Pipeline

A replayable, staged pipeline that ingests a vendor contract and a risk framework, extracts clauses deterministically, scores every clause using an LLM, performs deep analysis on critical clauses, pauses for human review, and produces a negotiation briefing with all supporting audit artifacts.

---

## How to Run

### Step 1 — Navigate to the project

```bash
cd ~/Desktop/Deriv_final_assessment
```

### Step 2 — Run the pipeline

```bash
python main.py run --provider mock --model heuristic-v1
```

The pipeline will pause mid-run and print the Stage 1 risk table, then ask:

```
Are there any clauses whose severity you want to override before generating the negotiation brief?
Enter clause number and new severity, or press Enter to continue.
```

- Press **Enter** to accept all AI scores as-is
- Or type `5 high` and press Enter to override clause 5 from critical to high, then press Enter again to continue

### Step 3 — Validate the outputs

```bash
python validate.py
```

Expected output:

```
VALIDATION PASSED
```

---

## Running With a Real LLM

To use OpenAI instead of the mock provider:

```bash
export OPENAI_API_KEY=your_key_here
python main.py run --provider openai --model gpt-4.1-mini
```

To use a local Ollama instance:

```bash
ollama pull llama3.1:8b
python main.py run --provider ollama --model llama3.1:8b
```

---

## What the Pipeline Does — Stage by Stage

### Inputs (read from disk, never hardcoded)

| File | Purpose |
|---|---|
| `contract.txt` | The raw vendor contract text |
| `risk_framework.json` | The allowed risk categories and severity level definitions |

---

### Stage 1 — Clause Extraction (pure code, no LLM)

Reads `contract.txt` and uses a regex to detect every numbered heading (`1. SERVICES`, `2. PAYMENT TERMS`, etc.). Splits the contract into clean structured records before any LLM is called.

**Output:** `extracted_clauses.json`

Each record contains:
```json
{
  "clause_number": "3",
  "clause_title": "DATA OWNERSHIP AND PROCESSING",
  "clause_text": "...",
  "word_count": 50
}
```

---

### Stage 2 — Risk Scoring (1 LLM call for all clauses)

Sends all extracted clauses and the full risk framework to the LLM in a single call. The LLM must assign each clause exactly one category and one severity from the allowed lists — it cannot invent new ones.

**Allowed categories:** `data_rights`, `financial_exposure`, `liability_cap`, `ip_ownership`, `termination_rights`, `dispute_resolution`, `unilateral_modification`

**Allowed severities:** `critical`, `high`, `medium`, `low`

**Output:** Stage 1 block added to `risk_analysis.json` for every clause

| Clause | Category | Severity |
|---|---|---|
| 1. SERVICES | unilateral_modification | medium |
| 2. PAYMENT TERMS | financial_exposure | high |
| 3. DATA OWNERSHIP AND PROCESSING | data_rights | **critical** |
| 4. CONFIDENTIALITY | data_rights | low |
| 5. LIABILITY | liability_cap | **critical** |
| 6. INTELLECTUAL PROPERTY | ip_ownership | high |
| 7. TERMINATION | termination_rights | high |
| 8. GOVERNING LAW | dispute_resolution | medium |
| 9. MODIFICATIONS | unilateral_modification | **critical** |
| 10. INDEMNIFICATION | financial_exposure | **critical** |

---

### Stage 3 — Deep Analysis of Critical Clauses (1 LLM call per critical clause)

For every clause rated `critical`, a separate dedicated LLM call is made — critical clauses are never batched together. Each call receives the clause text, its risk category, severity definition, and one-sentence summary from Stage 2.

Each call produces:
- **harm_mechanism** — exactly how the clause damages the client in practice
- **precedent_framing** — how to frame the pushback in the negotiation room
- **redline_suggestions** — 3 specific changes to demand
- **replacement_clause_text** — the fully rewritten safer clause in legal language

**Output:** Stage 2 block appended to each critical clause in `risk_analysis.json`

In this contract, clauses **3, 5, 9, and 10** received deep analysis (4 separate LLM calls).

---

### Stage 4 — Operator Review Checkpoint (human pause)

The pipeline prints the full risk table to the terminal and pauses. A human can review the AI's severity ratings and override any of them before the negotiation brief is generated.

Overrides are saved to `operator_overrides.json` and applied to the `final_severity` field of each clause. The original `stage_1.severity` is preserved unchanged so the AI's original judgement is always on record.

If no overrides are entered, `operator_overrides.json` contains an empty list and `final_severity` matches `stage_1.severity` for all clauses.

---

### Stage 5 — Negotiation Brief (1 final LLM call)

After operator review, a single LLM call generates the negotiation brief using the full risk analysis, deep analysis results, operator overrides, and final post-override severities.

**Output:** `negotiation_brief.md`

Sections:
- **Red Lines** — clauses with final severity `critical` (non-negotiable demands)
- **Priority Negotiations** — clauses with final severity `high`
- **Acceptable With Modification** — clauses with final severity `medium`
- **Standard / Accept** — clauses with final severity `low`
- **Opening Position** — 2-3 sentence framing statement for the negotiation call

---

### Stage 6 — Optional Outputs (pure code, no LLM)

Generated deterministically after the brief — no further LLM calls.

**`redlined_contract.md`** — The full contract with all critical clauses physically replaced by the safer `replacement_clause_text` from Stage 3, marked in bold.

**`clause_cross_references.json`** — Clause pairs that compound each other's risk. For example, Clause 3 (data rights) combined with Clause 7 (7-day deletion window) creates a critical combined risk around loss of client data control.

**`signature_risk_score.json`** — An overall sign-as-is risk score from 0 to 100 computed by a fixed deterministic formula:

```
score = min(100, critical×25 + high×12 + medium×5 + low×1)
```

For this contract: 4 critical + 3 high + 2 medium + 1 low = **100/100** (capped).

---

## Output Files

### Human-readable

| File | What it is |
|---|---|
| `negotiation_brief.md` | The main deliverable — talking points for the negotiation call, bucketed by severity |
| `redlined_contract.md` | Full contract with dangerous clauses replaced in bold with safer language |

### Structured data

| File | What it contains |
|---|---|
| `risk_analysis.json` | Master analysis file — all clause scores, deep analysis, market comparisons, final severities |
| `extracted_clauses.json` | The 10 parsed clauses with text and word counts |
| `operator_overrides.json` | Any severity changes made at the review checkpoint |
| `clause_cross_references.json` | Clause pairs that combine to create compounded risk |
| `signature_risk_score.json` | Overall risk score with formula, distribution, and justification |

### Audit trail

| File | What it contains |
|---|---|
| `llm_calls.jsonl` | One log line per LLM call — stage, clause number, timestamp, model, prompt hash, input and output artifact paths |
| `pipeline_state.json` | Current pipeline stage (`RESULTS_FINALISED` on a complete run) |
| `run_manifest.json` | Which input files were read and when the run started |

---

## Pipeline Stage Machine

The controller enforces this exact sequence and will error on any out-of-order transition:

```
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

---

## Total LLM Calls

| Call | Stage | Count |
|---|---|---|
| Stage 1 scoring | All clauses in one call | 1 |
| Stage 2 deep analysis | One call per critical clause | 4 (clauses 3, 5, 9, 10) |
| Stage 3 brief | One call for the full brief | 1 |
| **Total** | | **6** |

All other processing — clause extraction, override application, redline generation, cross-reference detection, risk score calculation — is deterministic code with no LLM involvement.

---

## Technical Notes

- Clause extraction uses a regex (`^\d+\.\s+.+$`) and is fully deterministic — same input always produces the same output
- The pipeline reads `contract.txt` and `risk_framework.json` from disk on every run — nothing is hardcoded
- The evaluator can replace both input files with equivalent fixtures and the pipeline will handle them correctly
- All markdown outputs carry an AI-generated analysis disclaimer and are explicitly marked as not legal advice
- The sign-as-is risk score is computed in code using a fixed formula — the LLM is never asked to produce a score
