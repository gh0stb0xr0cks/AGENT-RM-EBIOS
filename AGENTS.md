# Quick Navigation — AGENT-RM

Read CLAUDE.md first. This file is a navigation index only.

## By Task → module + rule triggered

| Task | Module | Rule Triggered |
|------|--------|----------------|
| Generate or modify corpus examples | `corpus/` | `.claude/rules/corpus/corpus-pipeline.md` |
| Training / merge / quantize scripts | `finetuning/` | `.claude/rules/finetuning/training-params.md` |
| Scoring, benchmark, report | `evaluation/` | `.claude/rules/finetuning/evaluation.md` |
| ChromaDB, embeddings, retrieval | `rag/` | `.claude/rules/orchestration/langchain-chains.md` |
| Workshop prompts A1→A5, guard | `prompts/` | `.claude/rules/orchestration/langchain-chains.md` |
| LangChain chains, session memory | `orchestration/` | `.claude/rules/orchestration/langchain-chains.md` |
| Ollama Modelfile, LM Studio config | `inference/` | `.claude/rules/inference/inference-config.md` |
| FastAPI routes, auth, logging | `app/api/` | `.claude/rules/app/api-security.md` |
| ANSSI compliance matrix | `compliance/` | `.claude/rules/compliance/anssi-qualification.md` |
| Unit tests, integration, e2e | `tests/` | `.claude/rules/tests/testing-standards.md` |

## Terminology Check Before Commit
```bash
make compliance-check
```
