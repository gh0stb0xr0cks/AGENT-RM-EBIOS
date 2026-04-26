# PROJECT TRACKING -- LLM EBIOS RM

> Last updated: April 27, 2026
> Context: solo developer + AI assistance

---

## 1. PROGRESS BY MODULE

| Module | Files | Implemented | Empty | Lines | Completion |
|--------|-------|-------------|-------|-------|------------|
| rag/ | 9 | 9 | 0 | 1,765 | **100%** |
| compliance/ | 4 | 3 | 1 | 1,208 | **75%** |
| orchestration/ | 10 | 5 | 5 | 673 | **50%** |
| evaluation/ | 7 | 2 | 5 | 226 | **29%** |
| tests/ | 10 | 3 | 7 | 897 | **30%** |
| corpus/ | 8 | 3 | 5 | 3,187 | **37%** |
| prompts/ | 11 | 0 | 11 | 0 | **0%** |
| inference/ | 7 | 0 | 7 | 0 | **0%** |
| finetuning/ | 9 | 0 | 9 | 0 | **0%** |
| app/ | 6 | 0 | 6 | 0 | **0%** |
| scripts/ | 5 | 0 | 5 | 0 | **0%** |
| docs/ | 6 | 0 | 6 | 0 | **0%** |
| **TOTAL** | **102** | **25** | **77** | **8,056** | **~27%** |

---

## 2. ESTIMATED REMAINING WORK (solo dev + AI)

The AI reduction factor is estimated at 0.5x-0.6x on pure Python code
(prompts, scripts, tests, API) and 0.8x on experimental work
(fine-tuning, corpus quality) where AI assists but does not replace judgment.

### LOT 1 -- Prompts & Inference configs (CRITICAL BLOCKER)
Unblocks entire orchestration -> LLM chain.

| Task | Estimate |
|------|----------|
| system_prompt.py (EBIOS expert system prompt) | 1d |
| A1_cadrage.py | 1d |
| A2_sources.py | 1d |
| A3_strategique.py | 1.5d |
| A4_operationnel.py (MITRE ATT&CK) | 1.5d |
| A5_traitement.py | 1d |
| guard_prompt.py + checklist.py | 0.5d |
| ollama_config.py + Modelfile + lm_studio_config | 0.5d |
| **Subtotal** | **8d** |

### LOT 2 -- Corpus Pipeline (~10,000 examples)
Prerequisite for fine-tuning. Most time-consuming.

| Task | Estimate | Status |
|------|----------|--------|
| 01_extract_pdf.py | 1d | **DONE** |
| 02_generate_synthetics.py (generation via LLM API) | 3d | **DONE** — 4 backends (claude/ollama/mistral/openrouter), ROOT path fixed, 109 examples generated across 70 files |
| 03_generate_counterexamples.py | 1.5d | stub |
| 04_quality_filter.py | 1d | stub |
| 05_format_chatml.py | 0.5d | stub |
| 06_stratified_split.py | 0.5d | stub |
| 07_validate_corpus.py | 1d | stub |
| Quality iterations (review, correction, regeneration) | 3d | IN PROGRESS (1,235/~6000 examples — A1 ✓, A2 ✓, A3 ✓, A4 partial, A5 stub) |
| **Subtotal** | **11.5d** | |

### LOT 3 -- Mistral 7B Fine-tuning
GPU experimentation. AI assists with code but not runs.

| Task | Estimate |
|------|----------|
| train_unsloth.py + YAML configs | 1.5d |
| train_llamafactory.py (alternative) | 1d |
| merge_lora.py | 0.5d |
| quantize_gguf.py (Q4_K_M + Q5_K_M) | 0.5d |
| verify_model.py | 0.5d |
| Hyperparameter experimentation (3-5 GPU runs) | 4d |
| Model quality iterations | 3d |
| **Subtotal** | **11.5d** |

### LOT 4 -- Complete Orchestration
Base exists (rag_chain.py, memory). Remaining: routers and validation.

| Task | Estimate |
|------|----------|
| atelier_chain.py (complete chain per workshop) | 1d |
| validation_chain.py (post-generation guard) | 1.5d |
| atelier_router.py | 0.5d |
| step_router.py | 0.5d |
| **Subtotal** | **3.5d** |

### LOT 5 -- Evaluation & Benchmark
Scoring exists (ebios_rules.py). Remaining: orchestration scripts.

| Task | Estimate |
|------|----------|
| run_benchmark.py | 1d |
| score_terminology.py + score_structure.py | 1d |
| score_coherence.py | 1d |
| generate_report.py (PDF report) | 1d |
| Reference testset creation (50-100 cases) | 2d |
| **Subtotal** | **6d** |

### LOT 6 -- Application (FastAPI + Streamlit UI)

| Task | Estimate |
|------|----------|
| main.py + FastAPI config | 0.5d |
| api/models.py (Pydantic schemas) | 1d |
| api/routes.py (CRUD all workshops) | 3d |
| api/dependencies.py (auth, sessions, security) | 1.5d |
| ui/streamlit_app.py | 3d |
| ui/components.py (radar, risk matrix) | 2d |
| **Subtotal** | **11d** |

### LOT 7 -- Tests, Compliance & Documentation

| Task | Estimate |
|------|----------|
| Remaining unit tests (5 files) | 2.5d |
| Remaining integration tests (2 files) | 1.5d |
| E2E tests (2 files) | 2d |
| ANSSI compliance tests (by EXI category) | 3d |
| generate_conformity_report.py | 1d |
| Utility scripts (health, export, download) | 1d |
| Technical documentation (6 files) | 2d |
| **Subtotal** | **13d** |

### TIME SUMMARY

| Lot | Days | % Total |
|-----|------|---------|
| LOT 1 - Prompts & Inference | 8d | 12% |
| LOT 2 - Corpus Pipeline | 11.5d | 17% |
| LOT 3 - Fine-tuning | 11.5d | 17% |
| LOT 4 - Orchestration | 3.5d | 5% |
| LOT 5 - Evaluation | 6d | 9% |
| LOT 6 - Application | 11d | 16% |
| LOT 7 - Tests & Compliance | 13d | 19% |
| **Gross subtotal** | **65d** | |
| Contingency (+15%) | 10d | |
| **ESTIMATED TOTAL** | **~75 working days** | |

Full-time: **~3.5 months** (15-16 weeks).
Part-time: **~7 months**.

---

## 3. INFRASTRUCTURE COST ESTIMATES (excluding labor)

### 3.1 GPU -- Fine-tuning

| Resource | Required specs | Estimated usage | Options | Cost |
|----------|---------------|----------------|---------|------|
| Mistral 7B QLoRA fine-tuning | GPU 24GB+ VRAM | ~50h (5 runs x 10h) | RTX 4090 local | 0 EUR |
| | | | A100 40GB cloud (RunPod/Lambda) | ~75-100 EUR |
| | | | Google Colab Pro+ | ~50 EUR/month x 2 = 100 EUR |
| Synthetic corpus generation | GPU or API | ~30h generation | Via local Ollama (Mistral 7B) | 0 EUR |
| | | | Via OpenRouter/Together API | ~30-50 EUR |

**Local GPU scenario (RTX 4090/A6000): 0 EUR**
**Full cloud scenario: 100-200 EUR**

### 3.2 Embeddings API

| Service | Usage | Unit cost | Total cost |
|---------|-------|-----------|------------|
| OpenRouter (intfloat/multilingual-e5-base) | ~5M tokens (full indexing + iterations) | ~0.002 EUR/1K tokens | ~10 EUR |
| OpenRouter (corpus generation if API) | ~20M tokens | ~0.50 EUR/1M tokens | ~10 EUR |

**API subtotal: ~10-20 EUR**

### 3.3 Models to Download

| Model | Size | Cost |
|-------|------|------|
| Mistral-7B-Instruct-v0.3 (base FT) | ~14 GB (FP16) | Free (HuggingFace) |
| nomic-embed-text (Ollama, local fallback) | ~275 MB | Free (Ollama pull) |
| GGUF export (Q4_K_M) | ~4.5 GB | Produced locally |
| GGUF export (Q5_K_M) | ~5.5 GB | Produced locally |

**Models subtotal: 0 EUR** (all open-source Apache 2.0 / MIT)

### 3.4 Storage & Tools

| Item | Estimate |
|------|----------|
| Additional disk storage (~50 GB models + data) | 0 EUR (local) |
| ChromaDB (vector DB ~350 MB target) | 0 EUR (local) |
| GitHub (private repo if needed) | 0 EUR (free) |
| LM Studio (inference interface) | 0 EUR (free) |
| Ollama (local serving) | 0 EUR (free) |

**Tools subtotal: 0 EUR**

### 3.5 TOTAL INFRASTRUCTURE COST

| Scenario | Description | Total cost |
|----------|-------------|------------|
| **Optimal (local GPU)** | RTX 4090 or equivalent already available, local Ollama for corpus | **10-20 EUR** |
| **Intermediate** | Colab Pro+ for FT, local Ollama for rest | **110-150 EUR** |
| **Full cloud** | Cloud GPU rental + APIs for everything | **200-300 EUR** |

---

## 4. CRITICAL PATH (dependency order)

```
Week 1-2  : LOT 1 (prompts + inference)
            -> Unblocks orchestration chain
           
Week 2-3  : LOT 4 (orchestration)
            -> Functional end-to-end RAG->prompts->LLM pipeline
           
Week 3-6  : LOT 2 (corpus)
            -> 10,000 training examples generated and validated
           
Week 6-9  : LOT 3 (fine-tuning)
            -> GGUF model exported and verified
           
Week 8-10 : LOT 5 (evaluation) [parallelizable with end of LOT 3]
            -> Score >= 80% on EBIOS benchmark
           
Week 9-13 : LOT 6 (application) [parallelizable with LOT 5]
            -> Functional API + UI
           
Week 13-16: LOT 7 (tests + compliance + docs)
            -> Test coverage >= 80%, ANSSI compliance matrix
```

**Bottleneck: LOT 2 + LOT 3** (corpus + fine-tuning).
This is where real time exceeds pure dev time: GPU runs take hours and corpus quality requires manual iterations.

---

## 5. IDENTIFIED RISKS

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|
| Insufficient corpus quality -> mediocre model | Very High | Medium | Strict filtering + counterexamples + iterative evaluation |
| Insufficient VRAM for Mistral 7B QLoRA | High | Low if 24GB+ | Reduce batch_size, use gradient checkpointing |
| Benchmark score < 80% after 3 runs | High | Medium | Increase corpus, adjust prompts, LoRA rank |
| Embedding model changes API/pricing | Low | Low | Fallback to local nomic-embed-text via Ollama |
| ANSSI qualification requires more than POC | Medium | High | Document POC limitations in dossier |

---

## 6. DELIVERABLES & POC MILESTONES (12 weeks)

| Ref | Deliverable | Dependency | Status |
|-----|-------------|------------|--------|
| L2 | corpus/datasets/ebios_rm_corpus.jsonl (~10K examples) | LOT 2 | IN PROGRESS (1,235 raw examples — A1: 251, A2: 237, A3: 659, A4: 69, A5: 19 — A4/A5 need completion) |
| L3 | Documented fine-tuning pipeline | LOT 3 | TODO |
| L4 | mistral-7b-ebios-rm-q4_k_m.gguf | LOT 3 | TODO |
| L5 | LM Studio configs + workshop prompts | LOT 1 | TODO |
| L6 | Methodological validation report | LOT 5 | TODO |

---

## 7. DEVELOPMENT SESSION LOG

| Date | Session | Work performed | Duration |
|------|---------|----------------|----------|
| 2026-03-31 | #1 | Complete RAG module: embedding_config aligned with AGENTS.md, shared OpenRouterEmbeddings, token-aware chunker, build_index (PDF+CSV+JSONL), add_documents, test_retrieval, formatting.py, AtelierContext, session_memory, chunk_formatter, 69 tests (unit+integration), compliance matrix updated, Makefile fixed | ~3h |
| 2026-04-26 | #2 | **corpus/**: Added OpenRouter as 4th generation backend to `02_generate_synthetics.py` (OPENROUTER_API_KEY, `_generate_openrouter()`, default model `mistralai/mistral-small-2603`). Fixed ROOT path bug (`parent` → `parents[1]`) so OUTPUT_DIR now correctly resolves to `corpus/raw/synthetics/`. Ran first generation pass: 109 examples produced across 70 JSONL files (A1-A5 × 14 sectors); A1 and A2 single-example targets mostly complete, A3-A5 multi-example targets partial. | ~2h |
| 2026-04-27 | #3 | **corpus/**: Ran second full generation pass with `02_generate_synthetics.py`. Total examples grew from 109 → **1,235** across 70 JSONL files. A1 complete (251 ex., ~18/sector, 13/14 at target), A2 complete (237 ex., ~15-20/sector, all sectors populated), A3 largely complete (659 ex., ~44-51/sector, all sectors populated). A4 partial (69 ex., uneven: sante=28, defense=11, others 1-4). A5 stub (19 ex., 0-2/sector). Generation progress tracked in `corpus/raw/.generation_progress.json`. Next: complete A4/A5 generation, then run `03_generate_counterexamples.py`. | ~1.5h |

---

*This file is the source of truth for project tracking.
Update it after each development session.*
