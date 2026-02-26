# Issues & Roadmap — Contextual Architect

## Completed ✅

### Phase 1: Data Collection
- [x] **CodeReviewer dataset integration** — Downloader + JSONL converter
- [x] **Custom PR extractor** — GitHub API scraper with quality scoring

### Phase 3: Multi-Agent Architecture (Core)
- [x] **Agent orchestration protocol** — Input/output schemas, context handoff, retry loop
- [x] **Historian Agent** — Convention detection, anti-pattern warnings, heuristic + LLM modes
- [x] **Architect Agent** — Directory mapping, utility discovery, file placement
- [x] **Planner Agent** — Structured plan generation with acceptance criteria
- [x] **Alignment Agent** — Validates plan against user intent
- [x] **Implementer Agent** — Full-context code generation
- [x] **Reviewer Agent** — Syntax, security (CWE denylist), linting, external tools
- [x] **Test Generator Agent** — Unit test creation from acceptance criteria
- [x] **Orchestrator** — Parallel discovery + sequential generation + retry loop
- [x] **Style Fingerprint** — Naming, indentation, logging, error handling extraction
- [x] **Safe Code Writer** — Permission-based file modification with backups
- [x] **Workspace** — Filesystem-as-memory (Manus technique)
- [x] **LLM Client** — 7 providers (Groq, Gemini, DeepSeek, OpenAI, Anthropic, Ollama, Mock)
- [x] **System Prompts** — 8 constraint-based prompts (CoAT, CWE denylist, 3-layer review)
- [x] **Clarification Handler** — Ambiguity resolution from Architect signals
- [x] **Feedback Reader** — Historical feedback loop (closes learning cycle)

### Phase 5: Testing & Validation
- [x] **245 unit tests** — All passing
- [x] **25 E2E contract tests** — All passing
- [x] **Evaluation harness** — Real-LLM testing with automated constraint checks
- [x] **Evaluation results** — 3/3 tasks, 31/32 constraints (96.9%) on Groq llama-3.3-70b

---

## Open — Priority 1 (Immediate)

### Issue: RAG Layer for Repo-Specific Context
**Labels**: `priority-critical`, `architecture`

Add vector store (Qdrant or ChromaDB) so agents can semantically search repo-specific PR history, conventions, and past reviews. This is the **patent differentiator**.

**Tasks**:
- [ ] Choose vector DB (Qdrant vs ChromaDB)
- [ ] Embed repo files + PR data using sentence-transformers
- [ ] Wire into Historian agent for semantic pattern search
- [ ] Wire into Planner for "similar past tasks" retrieval

---

### Issue: Fix Architect file naming
**Labels**: `bug`, `priority-high`

Architect always targets `feature.py` regardless of task. Should suggest descriptive names (e.g., `health.py`, `users.py`).

---

### Issue: Fix CWE-89 false positive
**Labels**: `bug`, `priority-medium`

Evaluation harness CWE-89 regex flags f-string error messages as SQL injection. Need to refine pattern to only match actual SQL queries.

---

## Open — Priority 2 (Short-term)

### Issue: MCP Integration
**Labels**: `priority-high`, `mcp`

Connect agents to live environment via MCP servers.

- [ ] `filesystem-mcp`: read_file, list_directory, write_file
- [ ] `github-mcp`: search_prs, get_pr_diff, get_file
- [ ] `terminal-mcp`: run_command, get_output

---

### Issue: Multi-file generation
**Labels**: `enhancement`

Currently generates one file per task. Complex tasks (like refactoring) need coordinated multi-file output.

---

### Issue: VS Code Extension
**Labels**: `enhancement`, `future`

Package as VS Code extension for real developer workflow integration.

---

## Open — Priority 3 (Research)

### Issue: Research Paper (IEEE)
**Labels**: `research`, `patent`

**Title**: Method and System for Multi-Agent Codebase-Aware Code Generation

**Novel Claims**:
1. Multi-agent swarm architecture for code generation with constraint prompts
2. Real-time codebase context injection via filesystem scanning
3. Architectural compliance validation using learned patterns
4. Rejection loop for iterative refinement with plan re-anchoring

**NOT claiming** (prior art):
- Training on PR data (Microsoft CodeReviewer)
- Code review generation

---

## Open — Priority 4 (Future Scope)

### Issue: Model Fine-Tuning
**Labels**: `future`, `training`

- [ ] LoRA fine-tuning on CodeReviewer dataset
- [ ] Repo-specific fine-tuning pipeline
- [ ] Evaluation vs base model (before/after comparison)

### Issue: Security Scanner Integration
**Labels**: `future`, `security`

- [ ] bandit for Python
- [ ] gosec for Go
- [ ] eslint-plugin-security for JS/TS
