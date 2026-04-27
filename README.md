# AGENT-RM — AI Assistant for ANSSI Risk Analysis

> **An open source language model specialized in the EBIOS Risk Manager method, deployable 100% offline (air-gapped), compliant with official ANSSI 2024 terminology.**

[![Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![Base Model](https://img.shields.io/badge/Model-Mistral_7B_Instruct_v0.3-orange.svg)](https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3)
[![Status](https://img.shields.io/badge/Status-POC-yellow.svg)]()
[![ANSSI EBIOS RM](https://img.shields.io/badge/Method-EBIOS_RM_2024-red.svg)](https://www.ssi.gouv.fr/guide/ebios-risk-manager-la-methode/)

---

## Overview

**AGENT-RM** is an open source AI assistant designed to help cybersecurity analysts and consultants conduct digital risk analyses using the [EBIOS Risk Manager](https://www.ssi.gouv.fr/guide/ebios-risk-manager-la-methode/) method published by ANSSI.

It is based on **Mistral 7B Instruct v0.3** fine-tuned on annotated EBIOS RM corpus examples, enhanced with a RAG (Retrieval-Augmented Generation) system indexing official ANSSI documentation. The entire system operates **100% offline** — no data leaves the organization's infrastructure.

```
┌──────────────────────────────────────────────────────┐
│  INTERFACE (LM Studio · FastAPI · Streamlit)         │
├──────────────────────────────────────────────────────┤
│  ORCHESTRATION (LangChain · ChromaDB · Prompts)      │
├──────────────────────────────────────────────────────┤
│  INFERENCE (Mistral 7B fine-tuned · llama.cpp)       │
└──────────────────────────────────────────────────────┘
          100% local — 100% offline — Apache 2.0
```

## Why This Project?

The EBIOS RM method is the French and European reference for digital risk assessment. It is recognized by ANSSI, compatible with ISO/IEC 27005:2022, and recommended for homologation and NIS2 compliance processes.

It is also perceived as **complex to implement**, particularly for:
- Organizations with less cybersecurity maturity approaching the method for the first time
- Consultants managing multiple analyses in parallel who need structuring support
- CISOs who want to document their analyses rigorously without mastering all the nuances of the 5 workshops

Generic LLM solutions (ChatGPT, Copilot...) do not know official ANSSI 2024 terminology, regularly confuse rating scales, and cannot be used for confidential analyses. This project addresses these three problems simultaneously.

---

## Key Features

- **5 EBIOS RM Workshops guide** : A1 Scope & Security Baseline, A2 Risk Sources, A3 Strategic Scenarios, A4 Operational Scenarios, A5 Risk Treatment
- **Deliverable generation** : business values tables, support assets, SR/OV pairs, attack paths, treatment plans
- **Terminology validation** : permanent compliance with official ANSSI 2024 terminology
- **Automatic calculation** : stakeholder dangerousness using the official ANSSI formula
- **100% offline mode** : no data leaves the infrastructure — ideal for confidential analyses

### Workshops Coverage

| Workshop | Content | Status |
|----------|---------|--------|
| **A1 — Scope & Security Baseline** | Missions, business values, support assets, dreaded events, severity, security baseline | 🟡 In progress |
| **A2 — Risk Sources** | SR/OV pairs identification, risk sources mapping | 🟡 In progress |
| **A3 — Strategic Scenarios** | Ecosystem, stakeholder dangerousness, attack paths, ecosystem measures | 🟡 In progress |
| **A4 — Operational Scenarios** | Operating modes, elementary actions, likelihood (express/standard/advanced methods), enriched by MITRE ATT&CK Enterprise / ICS / Mobile (v18.1) | 🟡 In progress |
| **A5 — Risk Treatment** | Risk treatment plan, residual risks, initial/residual risk map | 🟡 In progress |

### What the LLM Does

- Generates business values and support assets tables from context description
- Proposes SR/OV pairs adapted to the activity sector
- Builds strategic scenarios with attack paths
- Automatically calculates stakeholder dangerousness levels according to official ANSSI formula
- Proposes structured risk treatment plan with owners and deadlines
- Permanently validates terminology compliance with EBIOS RM 2024 method

---

## Technical Architecture

### Inference Layer

| Component | Role | Detail |
|-----------|------|--------|
| **Mistral 7B Instruct v0.3** | Base model | Apache 2.0 license, native French, 7.24B parameters |
| **llama.cpp** | Inference engine | CPU/GPU execution, GGUF format |
| **Ollama** | Local REST API | `http://localhost:11434`, OpenAI-compatible |
| **LM Studio** | User interface | Fine-tuned GGUF loading |
| **GGUF Q4_K_M** | Deliverable format | ~4.1 GB, 8 GB RAM sufficient on CPU |

### Orchestration Layer

| Component | Role | Detail |
|-----------|------|--------|
| **LangChain 0.3+** | LCEL pipeline | RAG chain + validation + memory |
| **ChromaDB** | Vector database | Persistent, offline; current corpus index ≈ 1 085 chunks (136 ANSSI + 949 MITRE) |
| **nomic-embed-text** | Embeddings | 768 dims, multilingual, local via Ollama |
| **BM25** | Lexical retrieval | Hybrid 70% semantic / 30% lexical |
| **MITRE ATT&CK source data** | A4 enrichment | Enterprise / ICS / Mobile v18.1 — tactics, techniques, software, groups, campaigns, mitigations |

### Fine-tuning Pipeline

| Step | Tool | Detail |
|------|------|--------|
| **Corpus** | Python scripts + Claude API | ~10,000 instruction/response pairs |
| **Fine-tuning** | Unsloth + TRL SFTTrainer | QLoRA r=16 α=32, 3 epochs |
| **Export** | llama.cpp convert | GGUF Q4_K_M + Q5_K_M |

---

## Technical Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.10+ | 3.11+ |
| RAM | 8 GB | 16 GB |
| GPU | — | NVIDIA RTX 3060+ (8 GB VRAM) |
| Storage | 10 GB | 20 GB |

### Hardware for Inference

| Configuration | RAM | VRAM | Throughput |
|---------------|-----|------|------------|
| CPU only (Q4_K_M) | 16 GB | — | ~5 tokens/s |
| GPU RTX 3060 (Q4_K_M) | 16 GB | 8 GB | ~40 tokens/s |
| GPU RTX 3090 (Q5_K_M) | 16 GB | 24 GB | ~60 tokens/s |

### Hardware for Fine-tuning

| GPU | VRAM | Duration (3 epochs) |
|-----|------|---------------------|
| NVIDIA A100 40 GB | ~22 GB | ~4–6 hours |
| 2× RTX 3090 24 GB | ~20 GB/GPU | ~6–8 hours |

**Software** : [Ollama](https://ollama.ai), [LM Studio](https://lmstudio.ai/) (optional)

---

## Project Structure

```
agent-rm/
├── CLAUDE.md                    # Main context for AI agents (Claude Code / OpenCode)
├── AGENTS.md                    # Quick navigation by module
├── ARCHITECTURE.md              # Layered architecture reference
├── PROJECT_TRACKING.md          # Session-by-session progress log
├── README.md
├── Makefile                     # Unified command interface
├── pyproject.toml               # Runtime + dev dependencies
├── docker-compose.yml
├── .pre-commit-config.yaml
│
├── corpus/                      # Corpus pipeline (~10,000 annotated examples)
│   ├── raw/
│   │   ├── anssi/               # ANSSI source PDFs + extracted .txt
│   │   ├── mitre/               # MITRE ATT&CK xlsx (enterprise/ics/mobile v18.1)
│   │   │                          + per-sheet JSON + rendered .txt
│   │   ├── synthetics/          # Generated Q/A — 5 ateliers × 14 sectors = 70 shards
│   │   └── index.jsonl          # ◆ Unified chunk index (ANSSI + MITRE)
│   ├── scripts/
│   │   ├── schema.py            # ◆ Corpus schema source of truth
│   │   ├── 00_extract_mitre_xlsx.py  # MITRE ATT&CK xlsx → JSON (atelier 4 enrichment)
│   │   └── 01_extract_pdf.py … 07_validate_corpus.py
│   ├── processed/               # Filtered, deduplicated JSONL
│   ├── datasets/                # train.jsonl · validation.jsonl · test.jsonl
│   └── validation/              # Expert review template + quality checklist
│
├── rag/                         # ChromaDB index + embeddings pipeline
│   ├── embeddings/              # chunker.py · embedding_config.py · openrouter_embeddings.py
│   ├── scripts/                 # build_index.py · add_documents.py · test_retrieval.py
│   ├── collections/             # Collection metadata
│   └── corpus_index/            # Frozen chunk store per release tag
│
├── finetuning/                  # QLoRA pipeline + GGUF export
│   ├── configs/                 # lora_config · quantization · training_args · unsloth_config
│   ├── scripts/                 # train_unsloth · train_llamafactory · merge_lora
│   │                              quantize_gguf · verify_model
│   ├── checkpoints/             # Training checkpoints (gitignored)
│   └── output/                  # Final GGUF artefacts (Git LFS)
│
├── inference/                   # Ollama + LM Studio runtime adapters
│   ├── configs/                 # ollama_config.py · lm_studio_config.json · inference_params.yaml
│   ├── modelfiles/              # Modelfile.ebios
│   └── scripts/                 # load_model · run_inference · benchmark_speed
│
├── prompts/                     # Hierarchical templates per atelier
│   ├── system/                  # system_prompt.{py,txt}
│   ├── ateliers/                # A1_cadrage.py → A5_traitement.py
│   ├── validation/              # guard_prompt.py · checklist.py
│   └── tests/                   # test_prompts.py
│
├── orchestration/               # LangChain chains + routing + memory
│   ├── chains/                  # atelier_chain · rag_chain · validation_chain
│   ├── routers/                 # atelier_router · step_router
│   ├── memory/                  # session_memory · atelier_context
│   └── utils/                   # chunk_formatter · formatting
│
├── app/                         # FastAPI + Streamlit
│   ├── main.py                  # FastAPI entry point
│   ├── api/                     # routes.py · models.py · dependencies.py
│   ├── ui/                      # streamlit_app.py · components.py
│   └── static/
│
├── evaluation/                  # EBIOS RM methodological benchmark
│   ├── benchmarks/              # ◆ ebios_rules.py · atelier_checks.py
│   ├── scripts/                 # run_benchmark · generate_report
│   │                              score_terminology · score_structure · score_coherence
│   ├── testsets/                # 500 test cases per atelier (A1→A5)
│   └── reports/                 # Generated benchmark reports
│
├── compliance/                  # ANSSI qualification traceability
│   ├── matrices/
│   │   ├── anssi_requirements.py # ◆ 128 official ANSSI requirements
│   │   └── compliance_matrix.py # Coverage matrix by module
│   └── scripts/
│       └── run_compliance_check.py
│
├── data/                        # Runtime stores (gitignored)
│   ├── chroma_db/               # Live ChromaDB SQLite + HNSW segments
│   └── session_cache/
│
├── docs/                        # Reference documentation
│   ├── ebios/                   # ANSSI source PDFs + MITRE TTPs CSV
│   ├── architecture/            # Per-layer design notes
│   └── specs/                   # Architecture overview · proposition technique
│
├── scripts/                     # Operator shell scripts
│   └── setup_env.sh · download_models.sh · run_training.sh
│      check_health.sh · export_deliverables.sh
│
└── tests/                       # Unit · Integration · E2E
    ├── conftest.py              # Shared fixtures
    ├── unit/                    # test_corpus_quality · test_formatting · test_prompts · test_scoring
    ├── integration/             # test_inference · test_rag_chain · test_validation_guard
    └── e2e/                     # test_atelier_flow · test_full_ebios_session
```

---

## Installation

```bash
# Clone the repository
git clone https://github.com/[your-username]/ebios-rm-llm.git
cd ebios-rm-llm

# Install environment
make setup

# Download Ollama models
ollama pull nomic-embed-text

# Verify installation
make health
```

---

## Usage

### LM Studio Interface (recommended)

1. Download [LM Studio](https://lmstudio.ai/) (version 0.3+)
2. Load `finetuning/output/mistral-7b-ebios-rm-q4_k_m.gguf`
3. Import `inference/configs/lm_studio_config.json`
4. Start a conversation with a workshop prompt

### FastAPI API

```bash
# Start the API
make serve

# Example — Workshop A1: business values generation
curl -X POST http://localhost:8000/api/atelier/A1 \
  -H "Content-Type: application/json" \
  -d '{
    "organisation": "University hospital, 3,000 beds",
    "secteur": "health",
    "etape": "B",
    "contexte": "Patient management IS (EHR)"
  }'
```

### Make Commands

```bash
# Environment
make setup              # Install complete environment (venv + dependencies)
make health             # Verify all services are operational

# Corpus pipeline
make extract-mitre      # [Step 0] MITRE ATT&CK xlsx → JSON (atelier 4 enrichment)
make build-corpus       # Execute full 0→7 corpus pipeline (depends on extract-mitre)
# → Deliverable: corpus/datasets/train.jsonl (~9,000 examples)

# Fine-tuning (GPU required)
make train              # Launch QLoRA fine-tuning (Unsloth)
make train-llamafactory # Alternative via LLaMA-Factory
make merge-export       # Merge LoRA weights + export GGUF Q4_K_M

# Evaluation
make evaluate           # Complete EBIOS RM benchmark (500 cases/ workshop)
# → Deliverable: evaluation/reports/validation_methodologique.pdf

# RAG
make build-rag          # Build ChromaDB index from ANSSI PDFs
make test-rag           # Verify retrieval quality

# Tests
make test               # All tests (unit + integration)
make test-unit          # Unit tests only (no GPU required)
make test-e2e           # End-to-end tests (model required)

# ANSSI Qualification
make compliance-check   # Verify compliance matrix consistency
make compliance-stats   # Display coverage statistics
make compliance-report  # Generate PDF compliance report

# Application
make serve              # Local FastAPI API (port 8000)
make serve-ui           # Streamlit UI (port 8501)
```

---

## Official EBIOS RM 2024 Terminology

This project strictly applies the terminology from the ANSSI 2024 guide version. EBIOS 2010 terms are explicitly prohibited in all code, prompts, and corpus.

| ❌ Never Use | ✅ Official EBIOS RM 2024 Term |
|-------------|-------------------------------|
| Essential assets | **Business values** |
| Assets | **Support assets** |
| Threats (alone) | **Risk sources** + **Targeted objectives** |
| PACS | **Risk treatment plan** |
| Essential/Critical assets | **Business values** or **Support assets** |

**Official rating scales** are also implemented:

- **Severity** : G1 (Minor) · G2 (Significant) · G3 (Serious) · G4 (Critical)
- **Likelihood** : V1 (Unlikely) · V2 (Likely) · V3 (Very likely) · V4 (Almost certain)
- **Stakeholder dangerousness PP** : (Dependence × Penetration) / (Security Maturity × Trust)

---

## ANSSI Qualification

This project aims for ANSSI qualification of EBIOS RM tools. The 128 official requirements from the ANSSI qualification repository are fully traced in the `compliance/` module.

### Current Compliance Status

| Status | Count | Description |
|--------|-------|-------------|
| ✅ DONE | 3 | Implemented and tested |
| 🟡 IN_PROGRESS | 41 | Implementation in progress |
| ⬜ TODO | 79 | To be implemented |
| ➖ N/A | 5 | SaaS only (offline POC out of scope) |
| **Total** | **128** | ANSSI Requirements |

31 **P0 (blocking)** requirements are being addressed as priority.

```bash
# Display real-time compliance status
make compliance-stats
```

Full matrix available in [`compliance/matrices/compliance_matrix.py`](compliance/matrices/compliance_matrix.py).

---

## Performance Targets (POC)

| Metric | Minimum Threshold | Target |
|--------|------------------|--------|
| Overall EBIOS RM compliance | 75% | **≥ 80%** |
| Official ANSSI terminology | 90% | **≥ 95%** |
| Cross-workshop consistency A1→A5 | 80% | **≥ 85%** |
| Factual hallucinations | ≤ 10% | **≤ 5%** |
| 5 workshops coverage | 100% | **100%** |

These metrics are automatically measured via `make evaluate` on 500 test cases per workshop (holdout, never seen during training).

---

## Contributing

Contributions are welcome, particularly on:

- **Validated corpus examples** : instruction/response pairs on real anonymized cases (any sector)
- **Beta tester practitioners** : EBIOS RM analysts to test the 5 workshops on their own contexts
- **Terminology review** : verify that prompts and corpus comply with ANSSI 2024 terminology
- **Integration tests** : complete test coverage on LangChain modules

```bash
# Fork + clone
git clone https://github.com/[your-username]/ebios-rm-llm.git
cd ebios-rm-llm

# Create a branch
git checkout -b feat/my-contribution

# Install in development mode
make setup

# Run tests before submitting
make test-unit
make compliance-check

# Submit a Pull Request
```

### Conventions

1. **Terminology** : all French text must use official EBIOS RM 2024 terms. `compliance/scripts/run_compliance_check.py` automatically verifies this.
2. **Tests** : every new module must include unit tests in `tests/unit/`.
3. **Schema** : every corpus example must comply with the schema defined in `corpus/scripts/schema.py`.
4. **Format** : `ruff check .` must pass without errors.

---

## Roadmap

| Horizon | Goal |
|---------|------|
| **M1–M5** | Corpus 10,000 examples + complete ChromaDB RAG index |
| **M5–M8** | Fine-tuning v1 + GGUF export + initial benchmark |
| **M8–M12** | Complete LangChain orchestration + validated A1-A5 prompts |
| **M12–M15** | FastAPI + ANSSI compliance P0 (31 requirements) |
| **M15–M17** | Beta testing with practitioners + expert validation |
| **M18** | Submit ANSSI qualification dossier |

---

## References

- [EBIOS Risk Manager Guide — ANSSI (2024)](https://www.ssi.gouv.fr/guide/ebios-risk-manager-la-methode/)
- [EBIOS RM Method Sheets — Le Supplément](https://www.ssi.gouv.fr/guide/ebios-risk-manager-la-methode/)
- [Club EBIOS](https://www.club-ebios.org/)
- [Mistral 7B Instruct v0.3 — HuggingFace](https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3)
- [ANSSI EBIOS RM Tools Qualification Repository](https://www.ssi.gouv.fr/)
- [NIS2 — French transposition](https://www.ssi.gouv.fr/entreprise/reglementation/cybersecurite-des-operateurs/la-directive-nis/)
- [ISO/IEC 27005:2022 — Information security risk management](https://www.iso.org/standard/80585.html)

---

## What This Project Is Not

- **Not a cybersecurity operational tool** (SIEM, EDR, vulnerability scanner)
- **Not a substitute for human expertise** : it assists the practitioner, does not replace them
- **Not yet certified or qualified** : ANSSI qualification process is in progress
- **Not a SaaS service** : deploys exclusively on-premises (air-gapped by design)

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

ANSSI reference documents (EBIOS RM guide, method sheets) are distributed under **Open License / Open Licence Etalab v1** and are not included in this repository. They must be downloaded directly from the [ANSSI website](https://www.ssi.gouv.fr/).

---

## Contact

For questions about the project, collaborations, or ANSSI qualification process, open a [GitHub issue](../../issues) or contact us via [Discussions](../../discussions).

If you are a certified EBIOS RM practitioner and wish to participate in model validation, your contribution is particularly valuable — please reach out.

---

## Disclaimer

**This project is in Proof of Concept (POC) phase.** It is not yet qualified by ANSSI. Model outputs must always be reviewed by a competent EBIOS RM practitioner before any use in homologation or formal risk analysis.

Use of this software does not substitute for a security homologation process or the certifications described on the ANSSI website.

---

<div align="center">

**AGENT-RM** · Open source project · Apache 2.0 License

*Building a sovereign AI assistant for digital risk analysis in France*

</div>
