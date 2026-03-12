<h1 align="center">MACRO</h1>
<p align="center"><strong>Multi-Agent Contextual Repository Orchestrator</strong></p>
<p align="center">An AI coding agent that writes production-grade code by learning your project's conventions, architecture, and evolution.</p>

<p align="center">
  <a href="#quick-install"><img src="https://img.shields.io/badge/tests-420%20passing-brightgreen" alt="Tests"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL%20v3-blue.svg" alt="License: AGPL v3"></a>
  <a href="#"><img src="https://img.shields.io/badge/pipeline-12%20stages-orange" alt="Pipeline"></a>
  <a href="#"><img src="https://img.shields.io/badge/providers-7%20supported-purple" alt="Providers"></a>
</p>

---

## Why MACRO?

- **$0 with free APIs**: Use Groq (30 req/min) or Gemini (15 req/min) free tiers. No subscription.
- **Zero config**: `cd` into your project, type `macro`. That's it. Language auto-detected, interactive mode auto-starts.
- **Works on any GitHub repo**: `macro --github owner/repo` clones and analyzes any public or private repository.
- **7 LLM providers**: Google Gemini, Groq, OpenAI, Anthropic, DeepSeek, Ollama, Mock.
- **12-stage pipeline**: Scan → graph → plan → validate → implement → review → test → write.
- **Code graph intelligence**: AST-based dependency graph finds callers, affected files, and impact chains.
- **Style-aware**: Learns your naming conventions, indentation, logging patterns, and error handling.
- **Senior-level code**: Every agent thinks as a Staff+ Engineer with a Security Specialist persona.
- **Permission-based**: Never writes a file without showing you the diff and asking first.
- **Self-hosted**: Runs fully offline with Ollama. Your code never leaves your machine.
- **Open source**: AGPL v3 licensed.

## Quick Install

```bash
git clone https://github.com/yuvraj707sharma/Contextual-Architecture-agentic-ai.git
cd Contextual-Architecture-agentic-ai
pip install -e ".[dev]"
```

### Set an API key (pick one — Gemini and Groq are free)

```bash
# Linux / macOS
export GROQ_API_KEY=your_key_here

# Windows CMD (no quotes!)
set GROQ_API_KEY=your_key_here
```

Or run the interactive setup wizard: `macro --setup`

## Usage

```bash
# Just cd into your project and type macro
cd myproject
macro
```

That's it. MACRO auto-detects the language, enters interactive mode, and you start chatting.

### More examples

```bash
# Analyze any GitHub repo
macro --github tiangolo/fastapi

# Single-shot: generate a feature
macro "Add JWT authentication middleware"

# Point at a different project
macro --repo /path/to/other/project

# Auto-approve all changes
macro "Add JWT auth" --yes

# Dry run — preview without writing
macro "Add health check" --dry-run

# Multi-provider: fast agents + smart planner
macro --provider groq --planner-provider google
```

### Inside Interactive Mode

```
╭──── macro v0.3.0  ·  groq  ·  python ────╮
│  repo  ./myproject                        │
│                                           │
│  scan → graph → plan → code → review →    │
│  test → write                             │
│                                           │
│  ask   questions about your code          │
│  build type what you want to build        │
│  help  show all commands                  │
╰───────────────────────────────────────────╯

  myproject                    groq · llama3-70b
  ╭─────────────────────────────────────────╮
  │ ❯ Add user authentication              │
  ╰─────────────────────────────────────────╯
```

Two modes — auto-detected from your input:
- **Chat**: "What does @auth.py do?" → analyzes your code and answers
- **Build**: "Add JWT authentication" → runs the full 12-stage pipeline

Use `@filename` to target existing files: `Add booking to @pricing.py`

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
    |-- Project Scanner ────────  Detects frameworks, runtime, production env
    |-- Graph Builder ──────────  AST-based code graph (calls, imports, inheritance)
    |
    |-- [Parallel Discovery] ──+
    |   |-- Historian           |  Detects conventions, anti-patterns
    |   |-- Architect           |  Maps structure, finds utilities
    |   |-- Style Analyzer      |  Extracts naming, indentation, logging
    |   |-- PR Searcher         |  Finds relevant past PRs
    |                           |
    |-- Clarification ─────────+  Detects auth/framework/DB conflicts
    |-- Impact Analyzer            Uses code graph to find affected files
    |-- Planner ───────────────+  Creates structured plan + acceptance criteria
    |-- Alignment                  Validates plan against user intent
    |                           
    |-- [Implementation Loop] ─+
    |   |-- Implementer         |  Generates code with full agent context
    |   |-- Reviewer            |  Validates syntax, security, linting
    |   |-- (retry if rejected) |  Re-reads plan from disk (Manus AI technique)
    |                           
    |-- Test Generator             Auto-generates tests from plan criteria
    |-- Safe Writer                Shows diff, asks permission, writes files
    |-- Shell Executor             Suggests + runs tests, lint, installs
    |-- Pipeline Report            GitHub Actions-style dashboard
```

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

| Feature | Copilot/Cursor | Aider/Cline | Claude Code | MACRO |
|---------|---------------|-------------|-------------|-------|
| Zero config | ✗ | ✗ | ✗ | **Yes** — `cd project && macro` |
| Style matching | File-level | Basic | Conversation | **AST fingerprint** |
| Code graph | ✗ | ✗ | ✗ | **Yes** — callers, dependents, impact chains |
| Conflict detection | ✗ | ✗ | ✗ | **Yes** — auth/framework/DB mismatches |
| GitHub repos | ✗ | ✗ | ✗ | **Yes** — `macro --github owner/repo` |
| Provider flexibility | Locked | Some | Locked | **7 providers** |
| Cost | $10-500/mo | $0 (BYOK) | $20-200/mo | **$0** with free tiers |
| Fully offline | ✗ | Partial | ✗ | **Yes** — Ollama |
| Open source | ✗ | ✅ | ✗ | **✅** AGPL v3 |

## Project Structure

```
contextual-architect/
├── agents/                     # Core multi-agent pipeline
│   ├── orchestrator.py         # Coordinates all 12 stages
│   ├── historian.py            # Convention detection
│   ├── architect.py            # Structure mapping
│   ├── planner.py              # Structured planning
│   ├── alignment.py            # Plan validation
│   ├── implementer.py          # Code generation
│   ├── reviewer.py             # Security + linting
│   ├── test_generator.py       # Test creation
│   ├── safe_writer.py          # Permission-based file writing
│   ├── graph_builder.py        # AST-based code graph
│   ├── impact_analyzer.py      # Graph queries for affected files
│   ├── shell_executor.py       # Sandboxed command execution
│   ├── github_resolver.py      # --github clone + language detection
│   ├── interactive.py          # Rich interactive CLI
│   ├── llm_client.py           # 7 provider support
│   ├── system_prompts.py       # Senior Engineer persona prompts
│   └── tests/                  # 420 unit tests
├── data_pipeline/              # PR evolution data collection
├── rag/                        # RAG layer (ChromaDB + AST chunking)
├── docs/                       # Getting started guide
└── examples/                   # Usage examples
```

## License

AGPL v3 — See [LICENSE](LICENSE).

## Support

- ⭐ **Star this repo** — helps others find the project
- 🐛 **Report bugs** — every issue makes MACRO better
- 🔀 **Contribute** — see [CONTRIBUTING.md](CONTRIBUTING.md)

Built by **Yuvraj Sharma** — [Follow on GitHub](https://github.com/yuvraj707sharma) for updates.
