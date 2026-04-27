# Architecture — AGENT RM

> A sovereign, air-gappable French-language assistant for conducting risk
> analyses according to the ANSSI EBIOS Risk Manager 2024 methodology.
> Built solo, 80% AI-assisted, targeting ANSSI qualification at M18.

---

## 1. Purpose & Scope

The system is a **domain-specialized small LLM** (Mistral 7B Instruct v0.3
fine-tuned with QLoRA) wrapped in a **retrieval-augmented orchestration
layer** that walks a user through the five EBIOS RM workshops
(**A1 → A5**) end-to-end, in fourteen business sectors, while enforcing
the canonical ANSSI vocabulary and risk-rating scales (G1–G4 / V1–V4).

The product must be runnable **fully offline** on commodity hardware
(LM Studio or Ollama, no API egress in production) so that organisations
subject to homologation duties (OIV, OSE, public administrations) can
operate it inside their own perimeter.

---

## 2. Design Principles

These principles govern every module decision and are non-negotiable:

1. **Single source of truth for the domain** — All ANSSI vocabulary,
   forbidden terms, scales, sector taxonomy and the canonical system
   prompt live in **`corpus/scripts/schema.py`**. No script ever
   redefines a constant; everything imports from it. The 128 official
   ANSSI requirements live in **`compliance/matrices/anssi_requirements.py`**.
2. **Air-gapped by default** — Production inference and RAG run with
   Ollama (or LM Studio) + ChromaDB on local hardware. Cloud APIs
   (Claude, OpenRouter, Lambda Labs) are tolerated only during
   bootstrap (corpus generation, embeddings) and fine-tuning runs.
3. **Modular re-trainability** — Adding new ANSSI guidance must not
   require a full re-train. The RAG index is incremental; the fine-tune
   is reserved for terminology and reasoning patterns.
4. **Compliance-traceable** — Every ANSSI security requirement
   (`EXI_S1`…`EXI_S6`, P0 markers) is tracked in
   **`compliance/matrices/compliance_matrix.py`** with a status,
   owning module and evidence pointer.
5. **Stratified everything** — Corpus splits, evaluation benchmarks
   and beta tests are stratified on `(atelier × sector)` so that no
   combination is ever silently under-represented.
6. **Reproducible runs** — Seeded RNG, pinned model hashes, frozen
   ChromaDB collections per release tag.

---

## 3. The Seven Layers

The system is best read top-down, from the user-facing surface to the
foundational data:

```
┌──────────────────────────────────────────────────────────────────────┐
│  L7  EXPERIENCE         Streamlit UI · CLI · API consumers           │
├──────────────────────────────────────────────────────────────────────┤
│  L6  INTERFACE          FastAPI · auth · audit log · rate-limit      │
├──────────────────────────────────────────────────────────────────────┤
│  L5  ORCHESTRATION      Atelier chain (A1–A5) · prompts · guards     │
├──────────────────────────────────────────────────────────────────────┤
│  L4  REASONING          Fine-tuned Mistral 7B (Ollama/LM Studio)     │
├──────────────────────────────────────────────────────────────────────┤
│  L3  RETRIEVAL          ChromaDB · embeddings · chunk index          │
├──────────────────────────────────────────────────────────────────────┤
│  L2  CORPUS PIPELINE    extract → generate → filter → split (7 stp)  │
├──────────────────────────────────────────────────────────────────────┤
│  L1  GROUND TRUTH       ANSSI PDFs · MITRE ATT&CK · sector contexts  │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
                  COMPLIANCE & GOVERNANCE (cross-cutting)
                  schema.py · compliance_matrix.py · evaluation/ · tests/
```

Each layer talks **only** to the layer immediately below it through a
narrow interface. The compliance / governance plane is cross-cutting:
every layer publishes evidence into it.

---

## 4. Repository Layout

The repository organises around the seven layers above. Each top-level
directory carries an **`AGENTS.md`** that documents conventions for
AI-assisted edits (used by Claude + OpenCode); the project root carries
**`CLAUDE.md`** as the master entry-point, with `PROJECT_TRACKING.md`
recording session-level progress.

```
agent-rm/
├── CLAUDE.md                ← Master AI playbook (root)
├── AGENTS.md                ← Cross-tool agent conventions
├── ARCHITECTURE.md          ← This document
├── PROJECT_TRACKING.md      ← Session-by-session progress log
├── README.md
├── pyproject.toml           ← Single dependency surface
├── Makefile                 ← Pipeline orchestration
├── docker-compose.yml
├── .pre-commit-config.yaml
├── .env.example
│
├── corpus/                  ← L1 + L2: data pipeline
│   ├── AGENTS.md
│   ├── raw/
│   │   ├── anssi/           ← Source ANSSI PDFs + extracted text
│   │   │                      (guide_ebios_rm_2024, fiches_methodes,
│   │   │                       matrice_rapport_sortie)
│   │   ├── mitre/           ← MITRE ATT&CK references
│   │   └── synthetics/      ← Generated Q/A, one JSONL per
│   │                          (atelier × sector) = 5 × 14 = 70 shards
│   ├── scripts/
│   │   ├── schema.py        ← THE single source of truth
│   │   ├── 01_extract_pdf.py
│   │   ├── 02_generate_synthetics.py
│   │   ├── 03_generate_counterexamples.py
│   │   ├── 04_quality_filter.py
│   │   ├── 05_format_chatml.py
│   │   ├── 06_stratified_split.py
│   │   └── 07_validate_corpus.py
│   ├── processed/           ← Filtered, deduplicated JSONL
│   ├── datasets/            ← train.jsonl · eval.jsonl · test.jsonl
│   └── validation/          ← Expert review template · quality checklist
│
├── rag/                     ← L3: retrieval
│   ├── AGENTS.md
│   ├── embeddings/          ← chunker.py · embedding_config.py
│   │                          openrouter_embeddings.py
│   ├── scripts/
│   │   ├── build_index.py   ← Incremental ChromaDB indexer
│   │   ├── add_documents.py
│   │   ├── inspect_chunks.py
│   │   └── test_retrieval.py
│   ├── collections/         ← ChromaDB collection metadata
│   └── corpus_index/        ← Frozen chunk store per release tag
│
├── finetuning/              ← L4: fine-tuning
│   ├── AGENTS.md
│   ├── configs/             ← lora_config.yaml · quantization.yaml
│   │                          training_args.yaml · unsloth_config.yaml
│   ├── scripts/
│   │   ├── train_unsloth.py        ← Primary QLoRA loop (Unsloth)
│   │   ├── train_llamafactory.py   ← Alternate loop (LLaMA-Factory)
│   │   ├── merge_lora.py           ← LoRA → merged HF model
│   │   ├── quantize_gguf.py        ← HF → GGUF for Ollama/LM Studio
│   │   └── verify_model.py
│   ├── checkpoints/         ← Training checkpoints (gitignored)
│   └── output/              ← Final GGUF artefacts (Git LFS)
│
├── inference/               ← L4 runtime adapters
│   ├── AGENTS.md
│   ├── configs/             ← inference_params.yaml · ollama_config.py
│   │                          lm_studio_config.json
│   ├── modelfiles/          ← Modelfile.ebios (Ollama)
│   └── scripts/             ← load_model.py · run_inference.py
│                              benchmark_speed.py
│
├── prompts/                 ← Per-atelier and system prompt templates
│   ├── AGENTS.md
│   ├── system/              ← system_prompt.{py,txt}
│   ├── ateliers/            ← A1_cadrage · A2_sources · A3_strategique
│   │                          A4_operationnel · A5_traitement
│   ├── validation/          ← guard_prompt.py · checklist.py
│   └── tests/               ← test_prompts.py
│
├── orchestration/           ← L5: chains, routing, memory, guards
│   ├── AGENTS.md
│   ├── chains/              ← atelier_chain · rag_chain · validation_chain
│   ├── routers/             ← atelier_router · step_router
│   ├── memory/              ← session_memory · atelier_context
│   └── utils/               ← chunk_formatter · formatting
│
├── app/                     ← L6 + L7: API and UI
│   ├── AGENTS.md
│   ├── main.py              ← FastAPI entry point
│   ├── api/                 ← routes.py · models.py · dependencies.py
│   ├── ui/                  ← streamlit_app.py · components.py
│   └── static/
│
├── evaluation/              ← Domain benchmark + scoring
│   ├── AGENTS.md
│   ├── benchmarks/          ← ebios_rules.py · atelier_checks.py
│   ├── scripts/             ← run_benchmark · generate_report
│   │                          score_terminology · score_structure
│   │                          score_coherence
│   ├── testsets/            ← A1..A5 × 500-case stratified JSONL
│   └── reports/             ← Generated benchmark reports
│
├── compliance/              ← Cross-cutting governance
│   ├── AGENTS.md
│   ├── matrices/
│   │   ├── anssi_requirements.py   ← 128 official ANSSI requirements
│   │   └── compliance_matrix.py    ← Status × module × evidence
│   └── scripts/
│       └── run_compliance_check.py
│
├── data/                    ← Runtime stores (gitignored)
│   ├── chroma_db/           ← Live ChromaDB SQLite + HNSW segments
│   └── session_cache/
│
├── docs/                    ← Reference documentation
│   ├── ebios/               ← ANSSI source PDFs + MITRE TTPs CSV
│   ├── architecture/        ← Per-layer design notes
│   └── specs/               ← Architecture overview · proposition
│
├── scripts/                 ← Operator shell scripts
│   ├── setup_env.sh · download_models.sh · run_training.sh
│   ├── check_health.sh · export_deliverables.sh
│
└── tests/
    ├── conftest.py          ← Shared fixtures
    ├── unit/                ← test_corpus_quality · test_formatting
    │                          test_prompts · test_scoring
    ├── integration/         ← test_inference · test_rag_chain
    │                          test_validation_guard
    └── e2e/                 ← test_atelier_flow · test_full_ebios_session
```

---

## 5. Module Relationships — Overview Diagram

The diagram below shows **how data flows** between modules. Solid
arrows are runtime dependencies; dashed arrows are build-time only.

```
                           ┌─────────────────────┐
                           │   ANSSI PDFs        │
                           │   MITRE ATT&CK      │
                           │   (corpus/raw)      │
                           └──────────┬──────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
        ▼ build-time                  ▼ build-time                  ▼ runtime
┌───────────────────┐       ┌───────────────────┐         ┌─────────────────┐
│  corpus/scripts   │       │  rag/scripts/     │ ◀──────┤  rag/embeddings │
│  01..07 pipeline  │       │  build_index.py   │         │  (chunker +     │
│  → datasets/      │       │  → ChromaDB       │         │   embeddings)   │
└────────┬──────────┘       └─────────┬─────────┘         └────────┬────────┘
         │                            │                            │
         ▼                            ▼ at query time              │
┌───────────────────┐       ┌─────────────────────┐                │
│  finetuning/      │       │  orchestration/     │ ◀──────────────┘
│  train_unsloth.py │       │  chains/rag_chain   │
│  → LoRA adapter   │       └──────────┬──────────┘
│  merge_lora.py    │                  │
│  quantize_gguf.py │                  │ top-k chunks
│  → GGUF (output/) │                  │
└────────┬──────────┘                  │
         │                             │
         ▼                             ▼
┌──────────────────────────────────────────────────┐
│            orchestration/                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │ atelier_   │→ │ atelier_   │→ │ validation │  │
│  │ router     │  │ chain      │  │ _chain     │  │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  │
│        │  prompts/ateliers/A1..A5      │         │
│        ▼               ▼               ▼         │
│  ┌──────────────────────────────────────────┐    │
│  │  prompts/validation/guard_prompt          │   │
│  │   (terminology · scales)                  │   │
│  └──────────────────┬───────────────────────┘    │
└─────────────────────┼────────────────────────────┘
                      ▼
            ┌───────────────────┐
            │   app/main.py     │  ← FastAPI
            │   app/api         │
            │   app/ui          │  ← Streamlit
            └─────────┬─────────┘
                      ▼
                  Web UI / CLI

         ╔══════════════════════════════════════════════╗
         ║  schema.py            (imported by all)      ║
         ║  anssi_requirements.py + compliance_matrix.py║
         ║      (referenced by every AGENTS.md)         ║
         ╚══════════════════════════════════════════════╝
```

Three artefacts are read **everywhere**:

- **`corpus/scripts/schema.py`** — the corpus pipeline, the prompt
  guardrails, the evaluation benchmarks and the validation tests all
  import from it. Changing a forbidden term here propagates atomically
  through the whole stack.
- **`compliance/matrices/anssi_requirements.py`** — the 128 ANSSI
  requirements as canonical Python data.
- **`compliance/matrices/compliance_matrix.py`** — every module
  declares which `EXI_S*` / P0 requirements it covers; the conformity
  reports under `evaluation/reports/` are derived from this matrix.

---

## 6. Module Responsibilities

This section documents what each module owns and what it explicitly
does **not** own.

### 6.1 `corpus/` — Data pipeline (L1 + L2)

**Owns.** PDF extraction, synthetic Q/A generation across 14 sectors
and 5 ateliers (one JSONL shard per pair under `raw/synthetics/`),
counterexample creation (intentionally wrong answers labelled for
DPO-style alignment), terminology filtering, ChatML formatting,
stratified train/eval/test splits, and final validation.

**Pipeline.** Seven numbered scripts run in order, each consuming the
previous step's output. The `Makefile` exposes `make build-corpus`
covering steps 1–2, with later steps invoked explicitly. Each script
is independently re-runnable — output paths are deterministic.

**Does not own.** The fine-tuning loop, the inference engine, or the
RAG index — those read `corpus/datasets/` and `corpus/raw/anssi/` but
do not write back into them.

### 6.2 `rag/` — Retrieval (L3)

**Owns.** Chunking strategy (semantic-aware, ~512 tokens with overlap,
in `embeddings/chunker.py`), embedding configuration
(`embeddings/embedding_config.py`, plus an OpenRouter adapter for
build-time embedding generation), ChromaDB collection lifecycle, and
the retrieval API consumed by the orchestration `rag_chain`.

**Incremental.** `scripts/build_index.py` and `scripts/add_documents.py`
support adding new chunks without rebuilding from scratch — critical
for ANSSI guidance updates that arrive mid-project. The live store
sits in `data/chroma_db/`; frozen snapshots per release tag live in
`rag/corpus_index/`.

**Does not own.** The corpus itself. RAG reads from `corpus/raw/anssi`,
`corpus/raw/mitre`, `docs/ebios/` and any user-supplied document paths.

### 6.3 `finetuning/` + `inference/` — Fine-tuning and runtime (L4)

**`finetuning/` owns.** The QLoRA training loop (Unsloth as primary,
LLaMA-Factory as alternative), conversion of LoRA adapters to a merged
HF model and then to GGUF format consumable by Ollama / LM Studio
(`merge_lora.py`, `quantize_gguf.py`), and a model-verification step
(`verify_model.py`). Configs live in `finetuning/configs/` (LoRA,
quantization, training args, Unsloth-specific tuning).

**`inference/` owns.** Runtime adapters: an Ollama Modelfile
(`modelfiles/Modelfile.ebios`), an LM Studio config, common inference
parameters, and helper scripts to load, run and benchmark the
deployed model.

**Promotion criterion.** A checkpoint reaches production iff it scores
at the `ACCEPTANCE_THRESHOLDS` defined in `evaluation/benchmarks/`
**and** zero terminology violations on the regression set.

**Does not own.** The benchmark itself — that lives in `evaluation/`.

### 6.4 `prompts/` + `orchestration/` — Atelier chains (L5)

**`prompts/` owns.** The canonical system prompt (`system/`), one
prompt module per atelier (`ateliers/A1_cadrage.py` …
`A5_traitement.py`), and the validation/guard prompt
(`validation/guard_prompt.py`, plus a `checklist.py`). A small
`tests/` ensures the templates render and respect terminology.

**`orchestration/` owns.** The atelier execution graph
(`chains/atelier_chain.py`), the RAG step (`chains/rag_chain.py`),
the validation guard (`chains/validation_chain.py`), routers that
select the right atelier and step (`routers/`), session-level memory
(`memory/session_memory.py`, `memory/atelier_context.py`), and
formatting utilities for chunks and outputs (`utils/`).

**Failure modes.** The validation chain returns a repair prompt to
the atelier chain on terminology or scale violations; after the
configured retry budget the chain surfaces an explicit error to the
user rather than producing non-conformant output.

**Does not own.** Authentication, persistence, or audit logging —
those live in `app/`.

### 6.5 `app/` — API and UI (L6 + L7)

**Owns.** A FastAPI application (`main.py`) with routers under
`api/routes.py`, request/response schemas (`api/models.py`), shared
dependencies (`api/dependencies.py`), and a Streamlit UI
(`ui/streamlit_app.py` + `ui/components.py`) sufficient to demo full
atelier runs. Auth, audit log and rate-limit responsibilities are
declared here in scope and being progressively wired in (tracked
against `EXI_S1`/`EXI_S2`/`EXI_S5` in the compliance matrix).

**Deployment.** A 2 vCPU / 4 GB / 40 GB SSD VPS (Infomaniak or OVH)
with TLS termination, fail2ban, automatic security updates. The LLM
itself runs on a separate, more capable host (or co-located with GPU
during demos), driven via Ollama or LM Studio.

**Does not own.** Domain logic — every `/atelier/*` endpoint is a
thin wrapper around an `orchestration/chains/*` call.

### 6.6 `evaluation/` — Domain benchmark

**Owns.** The EBIOS rules engine (`benchmarks/ebios_rules.py`) and
per-atelier checks (`benchmarks/atelier_checks.py`), the test sets
(`testsets/A1..A5_*_500.jsonl`, 500 stratified cases per atelier),
and the scoring scripts: terminology, structure, coherence, plus a
reporter (`scripts/generate_report.py`) that materialises results
into `evaluation/reports/`.

**Gate.** `make evaluate` runs the full benchmark and is the
promotion gate for any new fine-tuned checkpoint.

### 6.7 `compliance/` — Governance (cross-cutting)

**Owns.** The 128 ANSSI requirements as code
(`matrices/anssi_requirements.py`) and the implementation matrix
(`matrices/compliance_matrix.py`) mapping every requirement
(`EXI_S1`…`EXI_S6`, the P0 markers) to: the implementing module, the
test that proves coverage, and a status (`covered` / `partial` /
`gap`). `scripts/run_compliance_check.py` runs the consistency check
exposed via `make compliance-check`, with `make compliance-stats` and
`make compliance-report` for reporting.

### 6.8 `tests/` — Validation

**Owns.** Unit tests per module (`unit/` — corpus quality, formatting,
prompts, scoring), integration tests that exercise inference, RAG and
the validation guard, and end-to-end scenarios (`e2e/`) covering a
single atelier flow and a full EBIOS session. Shared fixtures live
in `conftest.py`.

---

## 7. Schema as Single Source of Truth

`corpus/scripts/schema.py` exports — and all other code imports — the
following symbols:

| Symbol | Consumers | Role |
|---|---|---|
| `ATELIERS` | corpus pipeline · orchestration · tests | Canonical atelier list `[A1, …, A5]` |
| `SECTORS` · `SECTOR_LABELS` | corpus pipeline · benchmark | The 14 sector taxonomy |
| `SYSTEM_PROMPT` | finetuning · prompts · corpus | The canonical assistant role |
| `FORBIDDEN_TERMS` | corpus filter · guard prompt · validator | `{wrong → correct}` ANSSI terminology |
| `REQUIRED_TERMS_BY_ATELIER` | quality filter · validator | Minimum terminology per atelier |
| `SCALE_PATTERN` | guard prompt · quality filter | Regex `\b(G[1-4]|V[1-4])\b` |
| `GENERATION_TEMPLATES` · `GENERATION_THEMES` | corpus generator | Prompt templates for synthetic Q/A |
| `CorpusExample` · `Message` | every script handling JSONL | Typed dataclasses for pipeline records |

In parallel, `compliance/matrices/anssi_requirements.py` is the single
source of truth for the 128 ANSSI qualification requirements.
Everything else is local to its module.

---

## 8. Data Flow — A Typical Query

1. User sends *"Conduct atelier A3 for our hospital information system"*
   to the Streamlit UI (or a direct API client).
2. `app/api/routes` authenticates the session, opens an audit-log entry,
   and dispatches via `orchestration/routers/atelier_router` to
   `chains/atelier_chain` parameterised on `A3` and the session state.
3. The chain consults session memory (results of A1, A2 if present),
   builds a step-1 prompt from `prompts/ateliers/A3_strategique`, and
   calls `chains/rag_chain` for the top-k ANSSI chunks on strategic
   scenarios for healthcare.
4. The augmented prompt is sent to the LLM via the
   `inference/configs/ollama_config` (or LM Studio) client, which
   serves the fine-tuned Mistral 7B GGUF.
5. The response runs through `chains/validation_chain` and the guard
   prompt: terminology check (`FORBIDDEN_TERMS`), scale presence
   (`SCALE_PATTERN`), structural validation. Violations trigger a
   repair retry.
6. The chain advances through subsequent steps (path, party-stake
   dangerousness, G/V rating), accumulating into a structured
   atelier-A3 output stored in `orchestration/memory`.
7. `app/api` returns the result as JSON, appends a final audit entry,
   updates the session state.
8. The UI renders a printable A3 deliverable.

The same data path works offline: every component in steps 2–6 has
zero external network dependency in production.

---

## 9. Deployment Topology

```
┌────────────────────────────────────────────────────────────────┐
│  Operator perimeter (air-gapped or restricted network)         │
│                                                                │
│   ┌───────────────────┐         ┌──────────────────────────┐   │
│   │  VPS (app)        │ ──────▶ │  Inference host (GPU)    │   │
│   │  FastAPI + UI     │  HTTPS  │  Ollama / LM Studio      │   │
│   │  Audit log (WORM) │ (mTLS)  │  + Mistral 7B GGUF       │   │
│   │                   │         │  ChromaDB (read-only)    │   │
│   └───────────────────┘         └──────────────────────────┘   │
│                                                                │
└────────────────────────────────────────────────────────────────┘

       ▲ Build-time only (developer machine + cloud)
       │
       │ git push, signed model release
       │
┌──────┴──────────────────────────────────────────────────────────┐
│  Build perimeter                                                │
│   ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│   │ Dev laptop   │  │ Lambda Labs  │  │ GitHub (CI tests + │    │
│   │ corpus, RAG  │  │ A100 (8h)    │  │ compliance report) │    │
│   │ tests        │  │ fine-tune    │  │                    │    │
│   └──────────────┘  └──────────────┘  └────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

The split between **build** and **operator** perimeters is a hard
boundary: production never reaches out to the build perimeter, and
model promotion is an explicit, signed release artifact (LoRA
adapter → merged HF → GGUF → version-tagged Ollama Modelfile or LM
Studio config).

---

## 10. Compliance Architecture

The P0 markers and the six `EXI_S*` security families map to modules
as follows:

| ANSSI requirement family | Primary owner | Secondary owners |
|---|---|---|
| `EXI_S1` Identification | `app/api` (auth deps) | `app/main` |
| `EXI_S2` Authentication | `app/api` (auth deps) | `app/main` |
| `EXI_S3` Authorisation | `app/api` | `orchestration` |
| `EXI_S4` Confidentiality | `app/`, deployment | `rag/` (chunk store) |
| `EXI_S5` Traceability | `app/api` (audit) | `evaluation/reports` |
| `EXI_S6` Maintainability (MCS) | `compliance/`, CI | every module's `AGENTS.md` |
| Terminology fidelity (ANSSI) | `corpus/scripts/schema.py` | `prompts/validation` · `orchestration/chains/validation_chain` |
| Methodological fidelity (atelier steps) | `orchestration/chains` · `prompts/ateliers` | `evaluation/benchmarks` · `tests/e2e` |

Each module's `AGENTS.md` declares the specific markers it covers
(by ID), and `compliance/scripts/run_compliance_check.py` (invoked by
`make compliance-check`) checks that the matrix in
`compliance/matrices/compliance_matrix.py` is exhaustively covered
before any release can be tagged.

---

## 11. Evolution & Re-training Strategy

Three change classes, three different responses:

- **New ANSSI guidance / sector content** → re-index only.
  `rag/scripts/build_index.py` + `add_documents.py` ingest the new
  PDFs incrementally; no model re-train required. This is the most
  common case.
- **Terminology drift / vocabulary update** → edit `schema.py`, run
  `make build-corpus` and `make compliance-check`. The corpus filter
  catches old terms in regression; the validation chain enforces new
  ones at runtime. A re-train is optional, scheduled when the next
  QLoRA budget window opens.
- **Deep methodological change (e.g. EBIOS RM v2)** → full re-run
  of the corpus pipeline, one fine-tuning run on Lambda Labs
  (`make train` then `make merge-export`), benchmark gate
  (`make evaluate`), signed release. Budget: ~16 € + 1 day.

---

## 12. Glossary

| Term | Meaning |
|---|---|
| **EBIOS RM** | *Expression des Besoins et Identification des Objectifs de Sécurité — Risk Manager*, the ANSSI risk-analysis methodology |
| **ANSSI** | *Agence nationale de la sécurité des systèmes d'information*, the French national cybersecurity authority |
| **Atelier A1–A5** | The five steps of an EBIOS RM analysis (cadrage, sources de risque, scénarios stratégiques, scénarios opérationnels, traitement du risque) |
| **G1–G4 / V1–V4** | The official severity / likelihood scales |
| **DICP** | *Disponibilité, Intégrité, Confidentialité, Preuve* (security properties) |
| **P0** | A blocking compliance marker for homologation |
| **EXI_S*** | An ANSSI security requirement (Identification, Authentication, …) |
| **MCS** | *Maintien en Condition de Sécurité*, ongoing security maintenance |
| **OIV / OSE** | Operators of vital / essential importance, French regulated entities |
| **MITRE ATT&CK** | TTP knowledge base used to ground atelier A4 operational scenarios |
| **QLoRA** | Quantised Low-Rank Adaptation — the parameter-efficient fine-tuning technique used here |
| **GGUF** | Quantised model file format consumed by Ollama / LM Studio / llama.cpp |
| **ChatML** | The conversation format used by Mistral Instruct models during training |
