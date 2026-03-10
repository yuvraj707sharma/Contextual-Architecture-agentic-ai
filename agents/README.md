# Contextual Architect — Agent Framework

Multi-agent pipeline that writes production-grade, enterprise-ready code.

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
│               │ Implementer  │ ← LLM generates code           │
│               └──────┬───────┘                                 │
│                      ▼                                         │
│               ┌──────────────┐                                 │
│               │   Reviewer   │ ← syntax, security, lint        │
│               └──────┬───────┘                                 │
│              ┌───────┴────────┐                                │
│              │  Pass?         │                                │
│              │  YES → SafeWriter (show diff, ask, write)       │
│              │  NO  → feed errors → Implementer (retry)        │
│              └────────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
pip install -e ".[dev]"

# Set API key (pick one)
export GOOGLE_API_KEY=your_key     # FREE (15 req/min)
export GROQ_API_KEY=your_key       # FREE (30 req/min)

# Just point at a project — language auto-detected, interactive auto-starts
python -m agents --repo ./myproject

# Analyze any GitHub repo
python -m agents --github tiangolo/fastapi

# Single-shot
python -m agents "Add JWT authentication middleware" --repo ./myproject

# Auto-approve all changes
python -m agents "Add health check" --repo ./myproject --yes

# Dry run (preview without writing)
python -m agents "Add logging" --repo ./myproject --dry-run
```

### As Library

```python
import asyncio
from agents import Orchestrator, AgentConfig

config = AgentConfig(llm_provider="google")
orch = Orchestrator(config=config)

result = asyncio.run(orch.run(
    user_request="Add JWT authentication middleware",
    repo_path="/path/to/project",
    language="python",
))

print(result.generated_code)
print(result.target_file)
```

## Agents

| Agent | Role |
|-------|------|
| **StyleAnalyzer** | Fingerprints exact coding style (naming, indentation, logging, error handling) |
| **Historian** | Scans repo for patterns, conventions, and common mistakes |
| **Architect** | Maps directory structure, finds reusable utilities, picks target file |
| **ProjectScanner** | Detects frameworks, auth, databases, deployment platform, Docker, runtime |
| **ClarificationHandler** | Proactive conflict detection (auth/framework/DB mismatches) |
| **Planner** | Creates structured plan with acceptance criteria using full context |
| **Alignment** | Validates plan against user intent before implementation |
| **Implementer** | Generates code using LLM with ALL context + Senior Engineer persona |
| **Reviewer** | Validates syntax, security (CWE denylist), imports, lint |
| **TestGenerator** | Auto-generates tests from plan acceptance criteria |
| **SafeWriter** | 5-tier risk assessment, diff preview, permission-based file writing with backups |

## LLM Providers

| Provider | Cost | Quality | Setup |
|----------|------|---------|-------|
| Google Gemini | Free tier | Excellent | `GOOGLE_API_KEY` |
| Groq | Free tier | Fast inference | `GROQ_API_KEY` |
| DeepSeek | $0.14/1M tokens | Great for code | `DEEPSEEK_API_KEY` |
| OpenAI | $2.50-5/1M tokens | Excellent | `OPENAI_API_KEY` |
| Anthropic | $3-15/1M tokens | Best reasoning | `ANTHROPIC_API_KEY` |
| Ollama | FREE (local) | Good | `ollama pull qwen2.5-coder` |
| Mock | Free | Placeholder only | Default (no key needed) |

## Tests

```bash
pip install -e ".[dev]"
python -m pytest agents/tests/ -v
```

420 tests across 10 test files covering all agents, orchestrator, config, logging, clarification, and reasoning display.
