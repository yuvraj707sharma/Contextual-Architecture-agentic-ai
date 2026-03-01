<h1 align="center">MACRO</h1>
<p align="center"><strong>Multi-Agent Contextual Repository Orchestrator</strong></p>
<p align="center">An AI coding agent that writes production-grade code by learning your project's conventions, architecture, and evolution.</p>

<p align="center">
  <a href="#quick-install"><img src="https://img.shields.io/badge/tests-246%20passing-brightgreen" alt="Tests"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-green.svg" alt="License: Apache 2.0"></a>
  <a href="#"><img src="https://img.shields.io/badge/agents-9%20specialized-orange" alt="Agents"></a>
  <a href="#"><img src="https://img.shields.io/badge/providers-7%20supported-purple" alt="Providers"></a>
</p>

---

## Why MACRO?

- **$0 with free APIs**: Use Groq (30 req/min) or Gemini (15 req/min) free tiers. No subscription.
- **7 LLM providers**: Google Gemini, Groq, OpenAI, Anthropic, DeepSeek, Ollama, Mock. Bring your own key.
- **9 specialized agents**: Not one prompt — a full pipeline that plans, validates, and reviews before writing.
- **Style-aware**: Learns your naming conventions, indentation, logging patterns, and error handling.
- **Permission-based**: Never writes a file without showing you the diff and asking first.
- **Security enforcement**: CWE denylist blocks known vulnerability patterns before they reach your codebase.
- **Self-hosted**: Runs fully offline with Ollama. Your code never leaves your machine.
- **Open source**: Apache 2.0 licensed.

## Quick Install

```bash
git clone https://github.com/yuvraj707sharma/Contextual-Architecture-agentic-ai.git
cd contextual-architect
pip install -r requirements.txt
pip install -e .
```

### First-Time Setup (Interactive)

```bash
macro --setup
```

The setup wizard will:
- Check your system (Python version, dependencies)
- Ask which provider you want (Gemini and Groq are **FREE**)
- Test your API key
- Optionally configure a second provider for smarter planning
- Save everything permanently

### Manual Setup (Alternative)

```bash
# Set any one API key
export GOOGLE_API_KEY="your_key_here"     # or
export GROQ_API_KEY="your_key_here"       # or
export OPENAI_API_KEY="your_key_here"

# Save config
macro --save-config --provider google --api-key YOUR_KEY
```

## Usage

```bash
# Interactive mode (recommended)
macro -i --repo ./your-project --lang python

# Single-shot: generate a feature
macro "Add JWT authentication middleware" --repo ./myproject --lang python

# Multi-provider: fast agents + smart planner
macro -i --repo . --provider groq --planner-provider google

# See all options
macro --help
```

### Python API

```python
from agents import Orchestrator
from agents.llm_client import create_llm_client

llm = create_llm_client(provider="groq")
orchestrator = Orchestrator(llm_client=llm)
result = await orchestrator.run("Add a /health endpoint", repo_path=".", language="python")
print(result.generated_code)
```

## How It Works

```
User Request
    |
    |-- [Parallel Discovery] ----+
    |   |-- Historian             |  Detects conventions, anti-patterns
    |   |-- Architect             |  Maps structure, finds utilities
    |   |-- Style Analyzer        |  Extracts naming, indentation, logging
    |   |-- PR Searcher           |  Finds relevant past PRs
    |                             |
    |-- Planner ------------------+  Creates structured plan + acceptance criteria
    |-- Alignment                    Validates plan against user intent
    |                             
    |-- [Implementation Loop] ---+
    |   |-- Implementer           |  Generates code with full agent context
    |   |-- Reviewer              |  Validates syntax, security, linting
    |   |-- (retry if rejected)   |  Feeds errors back, re-reads plan from disk
    |                             
    |-- Test Generator               Auto-generates tests from plan criteria
    |-- Safe Writer                   Shows diff, asks permission before writing
```

**Key technique**: The plan is written to disk and re-read on every retry, pushing it into the LLM's recent attention window (inspired by [Manus AI](https://manus.im)).

## Supported Providers

| Provider | Model | Cost | Notes |
|----------|-------|------|-------|
| **Google Gemini** | gemini-2.5-flash | Free tier | Recommended for getting started |
| **Groq** | llama-3.3-70b | Free tier | Fast inference |
| **DeepSeek** | deepseek-chat | $0.14/1M tokens | Best cost-performance ratio |
| **OpenAI** | gpt-4o | Paid | Premium quality |
| **Anthropic** | claude-3.5-sonnet | Paid | Best reasoning |
| **Ollama** | any local model | Free (local) | Fully offline, air-gapped |
| **Mock** | — | Free | For testing without API keys |

Auto-detection: Set any `*_API_KEY` env var and MACRO finds the right provider.

## What Makes MACRO Different

| Feature | Copilot/Cursor | Claude Code | MACRO |
|---------|---------------|-------------|-------|
| Style matching | No | No | **Yes** — learns your conventions |
| Permission-based writing | No | No | **Yes** — shows diff, asks first |
| Security enforcement (CWE) | No | Partial | **Yes** — denylist blocks patterns |
| Provider agnostic | No | No | **Yes** — 7 providers |
| Self-hosted / offline | No | No | **Yes** — Ollama support |
| Multi-agent pipeline | No | No | **Yes** — 9 specialized agents |
| Open source | No | No | **Yes** — Apache 2.0 |
| Cost | $10-500/mo | $20-200/mo | **$0** with free tiers |

## Evaluation Results

Tested against a real FastAPI project (44 files) with **Groq llama-3.3-70b-versatile**:

| Task | Without RAG | With RAG | Time |
|------|------------|----------|------|
| Health check endpoint | 11/11 | 11/11 | 14.5s |
| Security input validation | 11/11 | 11/11 | 8.8s |
| Repository pattern refactor | 9/10 | **10/10** | 11.4s |
| **Total** | **31/32 (96.9%)** | **32/32 (100%)** | **34.7s** |

**Key finding**: RAG eliminated a CWE-89 false positive by providing the repo's actual SQLAlchemy ORM patterns.

```bash
# Run evaluation yourself
python evaluation_harness.py --provider groq --task simple-health-check

# Test against real GitHub PRs
python pr_evaluator.py --repo owner/repo --pr 42 --provider groq
```

## Project Structure

```
contextual-architect/
├── agents/                     # Core multi-agent pipeline (24 modules)
│   ├── orchestrator.py         # Coordinates all 9 agents
│   ├── historian.py            # Convention detection
│   ├── architect.py            # Structure mapping
│   ├── planner.py              # Structured planning
│   ├── alignment.py            # Plan validation
│   ├── implementer.py          # Code generation
│   ├── reviewer.py             # Security + linting
│   ├── test_generator.py       # Test creation
│   ├── safe_writer.py          # Permission-based output
│   ├── style_fingerprint.py    # Style extraction
│   ├── llm_client.py           # 7 provider support
│   ├── setup_wizard.py         # Interactive first-time setup
│   ├── trace_logger.py         # Distillation data collection
│   └── tests/                  # 246 unit tests
├── data_pipeline/              # PR evolution data collection
├── rag/                        # RAG layer (ChromaDB + AST chunking)
├── storage/                    # SQLite persistence
├── evaluation_harness.py       # Real-LLM testing framework
└── pr_evaluator.py             # GitHub PR evaluation
```

## Roadmap

- [x] 9-agent pipeline with parallel discovery
- [x] 7 LLM providers with auto-detection
- [x] RAG layer (ChromaDB + AST chunking)
- [x] Interactive setup wizard (`macro --setup`)
- [x] Trace logging for distillation data collection
- [x] 246 tests passing
- [ ] VS Code extension
- [ ] Model distillation (QLoRA from pipeline traces)
- [ ] SimpleMem long-term memory integration
- [ ] Multi-file refactoring support

## License

Apache License 2.0 — See [LICENSE](LICENSE)

## Author

**Yuvraj Sharma** — B.Tech 2nd Year
