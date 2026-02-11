# Contextual Architect — Agent Framework

Multi-agent pipeline that writes production-grade, enterprise-ready code.

## Architecture

```
User Request
     │
     ▼
┌─────────────────────────────────────────────────────┐
│           PARALLEL DISCOVERY PHASE                  │
│  ┌──────────────┬──────────────┬──────────────────┐ │
│  │ StyleAnalyzer│  Historian   │    Architect      │ │
│  │ (fingerprint)│ (patterns)   │ (structure)       │ │
│  └──────┬───────┴──────┬───────┴────────┬─────────┘ │
│         └──────────────┼────────────────┘           │
│                        ▼                            │
│               ┌──────────────┐                      │
│               │ Implementer  │ ← LLM generates code│
│               └──────┬───────┘                      │
│                      ▼                              │
│               ┌──────────────┐                      │
│               │   Reviewer   │ ← syntax, security,  │
│               └──────┬───────┘   lint, tests        │
│                      │                              │
│              ┌───────┴────────┐                     │
│              │  Pass?         │                     │
│              │  YES → SafeWriter (ask permission)   │
│              │  NO  → feed errors → Implementer     │
│              └────────────────┘                     │
└─────────────────────────────────────────────────────┘
```

## Quick Start

### As CLI Tool
```bash
# Install
pip install -e .

# Set API key (pick one)
export DEEPSEEK_API_KEY=sk-...          # cheapest ($0.14/1M tokens)
export OPENAI_API_KEY=sk-...            # GPT-4o
export ANTHROPIC_API_KEY=sk-ant-...     # Claude (best quality)

# Run
python -m agents "Add JWT authentication middleware" --repo ./myproject --lang python

# Or with the installed command
contextual-architect "Add caching layer" --repo ./myproject --lang go

# Dry run (see output without writing files)
python -m agents "Add health check" --repo ./myproject --dry-run

# Use a specific provider
python -m agents "Add logging" --repo ./myproject --provider ollama
```

### As Library
```python
import asyncio
from agents import Orchestrator, AgentConfig

config = AgentConfig(llm_provider="deepseek")
orch = Orchestrator(config=config)

result = asyncio.run(orch.run(
    user_request="Add JWT authentication middleware",
    repo_path="/path/to/project",
    language="python",
))

print(result.generated_code)
print(result.target_file)
print(result.validation.summary)
```

## Agents

| Agent | Role |
|-------|------|
| **StyleAnalyzer** | Fingerprints exact coding style (naming, indentation, logging, error handling) |
| **Historian** | Scans repo for patterns, conventions, and common mistakes |
| **Architect** | Maps directory structure, finds reusable utilities, picks target file |
| **Implementer** | Generates code using LLM with ALL context from other agents |
| **Reviewer** | Validates syntax, security, imports, lint — rejects bad code |
| **SafeWriter** | Permission-based file writing — never modifies without asking |

## LLM Providers

| Provider | Cost | Quality | Setup |
|----------|------|---------|-------|
| DeepSeek | $0.14/1M tokens | Great for code | `DEEPSEEK_API_KEY` |
| Ollama | FREE (local) | Good | `ollama pull deepseek-coder-v2:16b` |
| OpenAI | $2.50-5/1M tokens | Excellent | `OPENAI_API_KEY` |
| Anthropic | $3-15/1M tokens | Best reasoning | `ANTHROPIC_API_KEY` |
| Mock | Free | Placeholder only | Default (no key needed) |

## Tests

```bash
pip install -e ".[dev]"
python -m pytest agents/tests/ -v
```

181 tests across 8 test files covering all agents, orchestrator, config, and logging.
