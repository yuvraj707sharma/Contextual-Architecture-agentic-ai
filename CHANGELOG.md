# Changelog

All notable changes to MACRO are documented here.

## [0.3.0] — 2026-03-07

### Terminal UX Overhaul
- **Animated spinners** during LLM calls with elapsed time tracking
- **Simplified banner**: `macro v0.3.0 · groq · python` (replaced ASCII art)
- **Clean minimal output** — dim text, `✓ Done (2.1s)` format (no box-drawn panels)
- 7-stage pipeline display: `scan → graph → plan → code → review → test → write`

### Agent Prompt Quality
- Implementer now receives **graph intelligence** (AST callers/dependents)
- Implementer now receives **full plan markdown** with "follow exactly" instructions
- Implementer now receives **detected conflicts** (auth/framework mismatches)
- Stronger instructions for utility reuse and plan-following

### Infrastructure
- Added `rich>=13.0.0` as core dependency

## [0.2.0] — 2026-03-05

### Code Graph Intelligence (V2 Phase 1)
- **`graph_builder.py`**: AST-based code relationship graph — extracts functions, classes, methods, imports, calls, inheritance, decorators for Python, JS/TS, Go
- **`impact_analyzer.py`**: Query interface — callers, dependents, import chains, impact analysis
- **Pipeline integration**: Graph built after scanner, impact injected into planner

### Shell Executor (V2 Phase 2)
- **`shell_executor.py`**: Sandboxed command runner — SAFE/MEDIUM/BLOCKED tiers
- Auto-detects post-write actions (pytest, pip install, npm test)
- Permission model matching SafeCodeWriter

### Pipeline Dashboard (V2 Phase 2.5)
- **`pipeline_report.py`**: GitHub Actions-style results dashboard — Summary, Changes, CI Checks, Repository, Git panels
- Terminal display with box-drawing characters
- Auto-generated commit messages and git push commands

### Bug Fixes
- Fixed Architect's `feature.py` fallback naming — constraint-based routing to real filenames

## [0.1.0] — 2026-02-08

### Initial Release
- 9-agent pipeline: Scanner → Historian → Architect → Planner → Alignment → Implementer → TestGen → Reviewer → SafeWriter
- 7 LLM providers: Google Gemini, Groq, OpenAI, Anthropic, DeepSeek, Ollama, Mock
- Interactive CLI mode with intent detection (chat vs. build)
- Permission-based file writing with 5-tier risk levels and backups
- Proactive conflict detection (auth, framework, database, language)
- Production environment detection (Dockerfile, deployment configs, runtime)
- Style fingerprinting (naming, indentation, logging patterns)
- Rich reasoning display with per-agent icons
- Trace logging for future model distillation
- Interactive setup wizard (`macro --setup`)
- RAG layer (ChromaDB + AST chunking)
- 280 unit tests
