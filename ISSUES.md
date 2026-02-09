# GitHub Issues for Contextual Architect

This document tracks the key issues to create in the GitHub repository.
Create these as actual GitHub issues when ready.

---

## Phase 1: Data Collection

### Issue 1: Download and convert CodeReviewer dataset
**Labels**: `phase-1`, `data`, `priority-high`

**Description**:
Download Microsoft's CodeReviewer dataset from Zenodo and convert to our JSONL format.

**Tasks**:
- [ ] Run `python -m src.codereviewer --output data/codereviewer/`
- [ ] Validate output format matches our schema
- [ ] Filter for target languages (Go, Python, TypeScript)
- [ ] Document sample count and quality stats

**Links**:
- Paper: https://arxiv.org/abs/2203.09095
- Dataset: https://zenodo.org/record/6900648

---

### Issue 2: Extract supplementary data from gold-standard repos
**Labels**: `phase-1`, `data`, `priority-medium`

**Description**:
Use our custom extractor on 3-5 high-quality repos for supplementary training data.

**Tasks**:
- [ ] gofiber/fiber (Go patterns)
- [ ] fastapi/fastapi (Python patterns)
- [ ] vercel/next.js (TypeScript patterns)
- [ ] Merge with CodeReviewer data

---

## Phase 2: Training

### Issue 3: Set up training infrastructure
**Labels**: `phase-2`, `training`, `priority-high`

**Description**:
Set up cloud GPU environment for fine-tuning.

**Tasks**:
- [ ] Choose provider (RunPod vs Colab Pro+ vs Lambda)
- [ ] Install transformers, peft, bitsandbytes
- [ ] Test with small model first (7B)

---

## Phase 3: Multi-Agent Architecture ⭐ CORE

### Issue 4: Design agent orchestration protocol
**Labels**: `phase-3`, `architecture`, `priority-critical`

**Description**:
Define how agents communicate and share context.

**Tasks**:
- [ ] Define agent input/output schemas
- [ ] Design context handoff protocol
- [ ] Define rejection loop behavior

---

### Issue 5: Build Historian Agent
**Labels**: `phase-3`, `agent`, `priority-high`

**Tasks**:
- [ ] Implement PR history search via GitHub MCP
- [ ] Pattern extraction from past reviews
- [ ] Context summarization for Implementer

---

### Issue 6: Build Architect Agent
**Labels**: `phase-3`, `agent`, `priority-high`

**Tasks**:
- [ ] Directory structure mapping
- [ ] Dependency graph analysis
- [ ] "Where should this code go?" reasoning

---

### Issue 7: Build MCP servers (filesystem, github, terminal)
**Labels**: `phase-3`, `mcp`, `priority-high`

**Tasks**:
- [ ] filesystem-mcp: read_file, list_directory, write_file
- [ ] github-mcp: search_prs, get_pr_diff, get_file
- [ ] terminal-mcp: run_command, get_output

---

### Issue 8: Build Go orchestrator with parallel execution
**Labels**: `phase-3`, `orchestrator`, `priority-high`

**Tasks**:
- [ ] Goroutine-based parallel agent runner
- [ ] Context synthesis from multiple agents
- [ ] Timeout and error handling

---

## Phase 4: Security

### Issue 9: Integrate security scanners
**Labels**: `phase-4`, `security`

**Tasks**:
- [ ] gosec for Go
- [ ] bandit for Python
- [ ] eslint-plugin-security for JS/TS

---

## Phase 6: Patent

### Issue 10: Draft invention disclosure document
**Labels**: `phase-6`, `patent`, `priority-high`

**Description**:
**Title**: Method and System for Multi-Agent Codebase-Aware Code Generation

**Novel Claims**:
1. Multi-agent swarm architecture for code generation
2. Real-time codebase context injection via MCP
3. Architectural compliance validation using learned patterns
4. Rejection loop for iterative refinement

**NOT claiming** (prior art):
- Training on PR data (Microsoft did this)
- Code review generation
