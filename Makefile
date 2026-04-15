# ═══════════════════════════════════════════════════════
# Makefile — LLM EBIOS RM
# Main project commands
# ═══════════════════════════════════════════════════════

.PHONY: help setup build-corpus train merge-export evaluate build-rag test serve clean

PYTHON = python3
VENV = .venv
PIP = $(VENV)/bin/pip
PY = $(VENV)/bin/python

help: ## Display this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install complete environment (venv + dependencies)
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@echo "✓ Environment ready. Activate with: source $(VENV)/bin/activate"
	@echo "→ Verify Ollama is running: ollama serve"
	@echo "→ Download nomic-embed-text: ollama pull nomic-embed-text"

# ── Corpus pipeline (Steps 1-2) ────────────────────────
build-corpus: ## [Steps 1-2] Build complete training corpus
	$(PY) corpus/scripts/01_extract_pdf.py
	$(PY) corpus/scripts/02_generate_synthetics.py
	$(PY) corpus/scripts/03_generate_counterexamples.py
	$(PY) corpus/scripts/04_quality_filter.py
	$(PY) corpus/scripts/05_format_chatml.py
	$(PY) corpus/scripts/06_stratified_split.py
	$(PY) corpus/scripts/07_validate_corpus.py
	@echo "✓ Corpus built → corpus/datasets/"

# ── Fine-tuning (Step 3) ────────────────────────────────
train: ## [Step 3] Launch LoRA/QLoRA fine-tuning (GPU required)
	@echo "⚠ Checking corpus..."
	@test -f corpus/datasets/train.jsonl || (echo "❌ Missing corpus. Run 'make build-corpus'" && exit 1)
	@echo "🚀 Starting Unsloth fine-tuning..."
	$(PY) finetuning/scripts/train_unsloth.py
	@echo "✓ Training done → finetuning/checkpoints/"

train-llamafactory: ## [Step 3] Alternative: fine-tuning via LLaMA-Factory
	$(PY) finetuning/scripts/train_llamafactory.py

# ── Merge + Export GGUF (Step 4) ───────────────────────
merge-export: ## [Step 4] Merge LoRA + export GGUF Q4_K_M and Q5_K_M
	$(PY) finetuning/scripts/merge_lora.py
	$(PY) finetuning/scripts/quantize_gguf.py
	$(PY) finetuning/scripts/verify_model.py
	@echo "✓ Model exported → finetuning/output/"

# ── Evaluation (Step 5) ─────────────────────────────────
evaluate: ## [Step 5] Run complete EBIOS RM benchmark
	@test -f finetuning/output/mistral-7b-ebios-rm-q4_k_m.gguf || \
		(echo "❌ Missing GGUF model. Run 'make merge-export'" && exit 1)
	$(PY) evaluation/scripts/run_benchmark.py
	$(PY) evaluation/scripts/generate_report.py
	@echo "✓ Evaluation report → evaluation/reports/"

# ── RAG (Vector database) ───────────────────────────────
build-rag: ## Build ChromaDB index from EBIOS documents
	@echo "⚠ OPENROUTER_API_KEY must be set in .env"
	@echo "  Model: intfloat/multilingual-e5-base (768 dims)"
	@echo "  Sources: ANSSI PDF + MITRE CSV + synthetic corpus"
	$(PY) rag/scripts/build_index.py --reset --all-sources
	@echo "✓ RAG index built → data/chroma_db/"

test-rag: ## Test ChromaDB retrieval quality
	$(PY) rag/scripts/test_retrieval.py

# ── Tests ────────────────────────────────────────────────
test: test-unit test-integration ## Run unit + integration tests
	@echo "✓ Tests done"

test-unit: ## Unit tests (no GPU required)
	$(VENV)/bin/pytest tests/unit/ -v --tb=short

test-integration: ## Integration tests (Ollama must be running)
	$(VENV)/bin/pytest tests/integration/ -v --tb=short

test-e2e: ## End-to-end tests (GGUF model loaded required)
	$(VENV)/bin/pytest tests/e2e/ -v --tb=short -s

# ── Application ──────────────────────────────────────────
serve: ## Start local FastAPI API (port 8000)
	$(VENV)/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

serve-ui: ## Start Streamlit UI (port 8501)
	$(VENV)/bin/streamlit run app/ui/streamlit_app.py

# ── Deliverables ─────────────────────────────────────────
export-deliverables: ## Package deliverables L2-L6 for delivery
	bash scripts/export_deliverables.sh

# ── Utilities ────────────────────────────────────────────
health: ## Verify all services are operational
	bash scripts/check_health.sh

clean: ## Clean temporary files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache/ htmlcov/ .coverage 2>/dev/null || true
	@echo "✓ Cleanup done"

# ── ANSSI Qualification ──────────────────────────────
compliance-check: ## Verify ANSSI compliance matrix consistency
	$(PY) compliance/scripts/run_compliance_check.py
	@echo "✓ Compliance check done"

compliance-report: ## Generate ANSSI compliance PDF report (qualification deliverable)
	$(PY) compliance/scripts/generate_conformity_report.py
	@echo "✓ Compliance report → compliance/docs/rapport_conformite_anssi.pdf"

compliance-stats: ## Display ANSSI requirements coverage statistics
	$(PY) compliance/matrices/compliance_matrix.py
