# Contextual Architect — Agent Framework

Multi-agent pipeline that writes production-grade, enterprise-ready code.

## Quick Start

```bash
pip install -e ".[dev]"

# Set API key (pick one)
export GROQ_API_KEY=your_key       # FREE (30 req/min)
export GOOGLE_API_KEY=your_key     # FREE (15 req/min)

# cd into any project and type macro
cd myproject
macro

# Or analyze a GitHub repo
macro --github tiangolo/fastapi

# Or single-shot
macro "Add JWT authentication middleware"
```

## Architecture

```
User Request
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│           PARALLEL DISCOVERY PHASE                              │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐ │
│  │ StyleAnalyzer│  Historian   │  Architect   │  Scanner     │ │
│  │ (fingerprint)│ (patterns)   │ (structure)  │ (env+deploy) │ │
│  └──────┬───────┴──────┬───────┴──────┬───────┴──────┬───────┘ │
│         └──────────────┼──────────────┼──────────────┘         │
│                        ▼              ▼                        │
│         ┌───────────────────────────────────┐                  │
│         │ ClarificationHandler (conflicts)  │                  │
│         └─────────────┬─────────────────────┘                  │
│                       ▼                                        │
│               ┌──────────────┐                                 │
│               │   Planner    │ ← full context from all agents  │
│               └──────┬───────┘                                 │
│                      ▼                                         │
│               ┌──────────────┐                                 │
│               │  Alignment   │ ← validates plan vs user intent │
│               └──────┬───────┘                                 │
│                      ▼                                         │
│               ┌──────────────┐                                 │
│               │ Implementer  │ ← code generation               │
│               └──────┬───────┘                                 │
│                      ▼                                         │
│               ┌──────────────┐                                 │
│               │   Reviewer   │ ← syntax, security, lint        │
│               └──────┬───────┘                                 │
│              ┌───────┴────────┐                                │
│              │  YES → SafeWriter (show diff, ask, write)       │
│              │  NO  → feed errors → Implementer (retry)        │
│              └────────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

## Agents

| Agent | Role |
|-------|------|
| **StyleAnalyzer** | Fingerprints coding style (naming, indentation, logging, error handling) |
| **Historian** | Scans repo for patterns, conventions, and common mistakes |
| **Architect** | Maps directory structure, finds reusable utilities, picks target file |
| **ProjectScanner** | Detects frameworks, auth, databases, Docker, runtime |
| **ClarificationHandler** | Proactive conflict detection (auth/framework/DB mismatches) |
| **Planner** | Creates structured plan with acceptance criteria |
| **Alignment** | Validates plan against user intent |
| **Implementer** | Generates code with Senior Engineer + Security Specialist persona |
| **Reviewer** | Three-layer interrogation: Logic → Security (CWE denylist) → Style |
| **TestGenerator** | Auto-generates tests matching project's test framework |
| **SafeWriter** | 5-tier risk assessment, diff preview, permission-based file writing |

## LLM Providers

| Provider | Cost | Setup |
|----------|------|-------|
| Google Gemini | Free tier | `GOOGLE_API_KEY` |
| Groq | Free tier | `GROQ_API_KEY` |
| DeepSeek | $0.14/1M tokens | `DEEPSEEK_API_KEY` |
| OpenAI | Paid | `OPENAI_API_KEY` |
| Anthropic | Paid | `ANTHROPIC_API_KEY` |
| Ollama | FREE (local) | `ollama pull qwen2.5-coder` |

## Tests

```bash
pip install -e ".[dev]"
python -m pytest agents/tests/ -v
```

420 tests across 10 test files.
