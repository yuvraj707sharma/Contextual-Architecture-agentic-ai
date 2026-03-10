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
- **7 LLM providers**: Google Gemini, Groq, OpenAI, Anthropic, DeepSeek, Ollama, Mock. Bring your own key.
- **12-stage pipeline**: Not one prompt — a full pipeline that scans, graphs, plans, validates, reviews, and tests before writing.
- **Works on any GitHub repo**: `--github owner/repo` clones and analyzes any public or private repository.
- **Auto-detects language**: No `--lang` flag needed — MACRO scans your files and figures it out.
- **Code graph intelligence**: AST-based dependency graph finds callers, affected files, and impact chains — deterministic, not LLM guesses.
- **Style-aware**: Learns your naming conventions, indentation, logging patterns, and error handling.
- **Senior-level code**: Every agent thinks as a Staff+ Engineer with a Security Specialist persona — CWE denylist, input validation, sad-path handling.
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

# Windows CMD
set GROQ_API_KEY=your_key_here
```

Or run the interactive setup wizard:

```bash
python -m agents --setup
```

## Usage

```bash
# Just point at a project — language auto-detected, interactive mode auto-starts
python -m agents --repo ./myproject

# Analyze any GitHub repo
python -m agents --github tiangolo/fastapi

# Private repos (set GITHUB_TOKEN)
python -m agents --github myorg/private-api

# Single-shot: generate a feature
python -m agents "Add JWT authentication middleware" --repo ./myproject

# Multi-provider: fast agents + smart planner
python -m agents --repo . --provider groq --planner-provider google

# Auto-approve all changes
python -m agents "Add JWT auth" --repo ./myproject --yes

# Dry run — preview without writing
python -m agents "Add health check" --repo ./myproject --dry-run

# See all options
python -m agents --help
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
    |-- Project Scanner ----------------  Detects frameworks, runtime, production env
    |-- Graph Builder ------------------  AST-based code graph (calls, imports, inheritance)
    |
    |-- [Parallel Discovery] ----+
    |   |-- Historian             |  Detects conventions, anti-patterns
    |   |-- Architect             |  Maps structure, finds utilities
    |   |-- Style Analyzer        |  Extracts naming, indentation, logging
    |   |-- PR Searcher           |  Finds relevant past PRs
    |                             |
    |-- Clarification Handler ----+  Detects auth/framework/DB conflicts
    |-- Impact Analyzer              Uses code graph to find affected files
    |-- Planner ------------------+  Creates structured plan + acceptance criteria
    |-- Alignment                    Validates plan against user intent
    |                             
    |-- [Implementation Loop] ---+
    |   |-- Implementer           |  Generates code with full agent context
    |   |-- Reviewer              |  Validates syntax, security, linting
    |   |-- (retry if rejected)   |  Feeds errors back, re-reads plan from disk
    |                             
    |-- Test Generator               Auto-generates tests from plan criteria
    |-- Safe Writer                   Shows diff, asks permission, writes files
    |-- Shell Executor                Suggests + runs tests, lint, installs
    |-- Pipeline Report               GitHub Actions-style dashboard + git push
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

| Feature | Copilot/Cursor | Aider/Cline | Claude Code | MACRO |
|---------|---------------|-------------|-------------|-------|
| Style matching | File-level context | Basic context | Conversation context | **AST fingerprint** — naming, indentation, logging patterns |
| Code graph | ✗ | ✗ | ✗ | **Yes** — deterministic AST callers, dependents, impact chains |
| Conflict detection | ✗ | ✗ | ✗ | **Yes** — auth/framework/DB mismatches caught before planning |
| GitHub repos | ✗ | ✗ | ✗ | **Yes** — `--github owner/repo` clones and analyzes |
| Language detection | Manual | Manual | Auto | **Auto** — scans file extensions |
| Provider flexibility | Locked | Some | Locked | **7 providers** — Gemini, Groq, OpenAI, Anthropic, DeepSeek, Ollama |
| Cost | $10-500/mo | $0 (BYOK) | $20-200/mo | **$0** with free Groq/Gemini tiers |
| Fully offline | ✗ | Partial | ✗ | **Yes** — Ollama local models, air-gapped |
| Pipeline transparency | Black box | Visible | Visible | **12-stage pipeline** with reasoning display |
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
│   ├── graph_builder.py        # AST-based code relationship graph
│   ├── impact_analyzer.py      # Graph queries for affected files
│   ├── shell_executor.py       # Sandboxed command execution
│   ├── github_resolver.py      # --github clone + language detection
│   ├── interactive.py          # Rich interactive CLI session
│   ├── llm_client.py           # 7 provider support
│   ├── system_prompts.py       # Senior Engineer persona prompts
│   └── tests/                  # 420 unit tests
├── data_pipeline/              # PR evolution data collection
├── rag/                        # RAG layer (ChromaDB + AST chunking)
├── docs/                       # Getting started guide
├── examples/                   # Usage examples
└── evaluation_harness.py       # Real-LLM testing framework
```

## License

AGPL v3 — See [LICENSE](LICENSE). You can read, modify, fork, and use MACRO for personal/educational use. Commercial SaaS use requires sharing modifications.

## Support

If MACRO saves you time, consider:

- ⭐ **Star this repo** — helps others find the project
- 🐛 **Report bugs** — every issue makes MACRO better
- 🔀 **Contribute** — see [CONTRIBUTING.md](CONTRIBUTING.md)

Built by **Yuvraj Sharma** — [Follow on GitHub](https://github.com/yuvraj707sharma) for updates.
