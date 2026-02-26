# Contextual Architect

> **An AI system that writes production-grade, enterprise-ready code by learning from project evolution and enforcing architectural compliance via multi-agent orchestration.**

[![Tests](https://img.shields.io/badge/tests-270%2B%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

## The Problem

Current AI coding tools (Cursor, Copilot, Replit) write code that **works in isolation** but **fails enterprise code review**. They don't understand your project's conventions, architecture, or the unwritten "we don't do it that way here" rules.

## Our Solution

Contextual Architect uses a **7-agent pipeline** that scans your codebase, learns its patterns, plans before generating, and validates before presenting — like having a senior engineer who's been at your company for 10 years.

| Existing Tools | Contextual Architect |
|----------------|---------------------|
| Isolated code snippets | Full project-aware features |
| No pattern learning | Learns conventions from your repo |
| Single model prompt | 7 specialized agents in parallel |
| Static context | Real-time codebase scanning |
| No security checks | CWE denylist + automated validation |

## Architecture

```
User Request
    │
    ├──► Historian ────► Detects conventions, anti-patterns, common mistakes
    ├──► Architect ────► Maps structure, finds utilities, suggests file placement
    ├──► Style Analyzer ► Extracts naming, indentation, logging, error patterns
    │        │
    │        ▼
    ├──► Planner ──────► Creates structured plan with acceptance criteria
    ├──► Alignment ────► Validates plan against user intent
    │        │
    │        ▼
    ├──► Implementer ──► Generates code with full context from all agents
    ├──► Reviewer ─────► Validates syntax, security, linting (CWE denylist)
    ├──► Test Generator ► Creates unit tests mapped to acceptance criteria
    │        │
    │        ▼
    └──► Safe Writer ──► Permission-based file output (never writes without consent)
```

**Key Technique**: The plan is written to disk and re-read on every retry, pushing it into the LLM's recent attention window (inspired by [Manus AI](https://manus.im)).

## Quick Start

### 1. Install
```bash
git clone https://github.com/yuvraj707sharma/Contextual-Architecture-agentic-ai.git
cd contextual-architect
pip install -e .
```

### 2. Set your API key (any one provider)
```bash
# Groq (free, fast) — recommended for testing
export GROQ_API_KEY="gsk_..."

# Google Gemini (free tier)
export GOOGLE_API_KEY="..."

# Or: OPENAI_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY
```

### 3. Run
```bash
# CLI
python -m agents "Add a /health endpoint" --repo ./your-project --language python

# Python API
from agents import Orchestrator
from agents.llm_client import create_llm_client

llm = create_llm_client(provider="groq")
orchestrator = Orchestrator(llm_client=llm)
result = await orchestrator.run("Add a /health endpoint", repo_path=".", language="python")
print(result.generated_code)
```

## Supported LLM Providers

| Provider | Model | Cost | Notes |
|----------|-------|------|-------|
| **Groq** | llama-3.3-70b | Free tier | Fast inference, recommended for testing |
| **Google Gemini** | gemini-2.5-flash | Free tier | Good for coding tasks |
| **DeepSeek** | deepseek-chat | $0.14/1M tokens | Best cost-performance ratio |
| **OpenAI** | gpt-4o | Paid | Premium quality |
| **Anthropic** | claude-3.5-sonnet | Paid | Premium quality |
| **Ollama** | any local model | Free (local) | Privacy-first, offline |
| **Mock** | — | Free | For testing without API keys |

Auto-detection: Set any `*_API_KEY` env var and the system finds the right provider.

## Evaluation Results

Tested against a real FastAPI project with **Groq llama-3.3-70b-versatile**:

| Task | Status | Constraints | Time |
|------|--------|-------------|------|
| Health check endpoint | ✅ Pass | 11/11 | 42.8s |
| Security input validation | ✅ Pass | 11/11 | 17.1s |
| Repository pattern refactor | ✅ Pass | 9/10 | 25.9s |
| **Total** | **3/3** | **31/32 (96.9%)** | **85.8s** |

Automated constraint checks include: CWE-502 (no eval/exec), CWE-89 (no SQL injection), CWE-78 (no OS injection), pattern compliance, and agent output validation.

```bash
# Run evaluation yourself
python evaluation_harness.py --provider groq --task simple-health-check
```

## Project Structure

```
contextual-architect/
├── agents/                     # Core multi-agent pipeline (24 modules)
│   ├── orchestrator.py         # Coordinates all agents
│   ├── historian.py            # Convention detection
│   ├── architect.py            # Structure mapping
│   ├── planner.py              # Structured planning
│   ├── alignment.py            # Plan validation
│   ├── implementer.py          # Code generation
│   ├── reviewer.py             # Security + linting
│   ├── test_generator.py       # Test creation
│   ├── safe_writer.py          # Permission-based output
│   ├── style_fingerprint.py    # Style extraction
│   ├── system_prompts.py       # 8 constraint-based prompts
│   ├── llm_client.py           # 7 provider support
│   ├── clarification_handler.py # Ambiguity resolution
│   ├── feedback_reader.py      # Learning loop
│   └── tests/                  # 245 unit tests
├── data_pipeline/              # PR evolution data collection
│   └── src/
│       ├── pr_evolution/       # Custom GitHub PR extractor
│       └── codereviewer/       # Microsoft CodeReviewer dataset
├── evaluation_harness.py       # Real-LLM testing framework
├── test-projects/              # FastAPI test project for evaluation
└── evaluation_results/         # JSON results + generated code
```

## Progress

- [x] **Phase 1**: Data pipeline (PR extractor + CodeReviewer dataset)
- [x] **Phase 3**: Multi-agent pipeline (7 agents + orchestrator)
- [x] **Phase 3**: 7 LLM providers supported
- [x] **Phase 3**: Constraint prompts (CWE denylist, CoAT reasoning)
- [x] **Phase 3**: Feedback loop (clarification + learning)
- [x] **Phase 5**: Evaluation harness (96.9% constraint compliance)
- [x] **270+ tests** passing
- [ ] **Phase 2**: Model fine-tuning (LoRA — future scope)
- [ ] **Phase 4**: Deep security integration (bandit, gosec)
- [ ] **RAG Layer**: Vector store for repo-specific PR history
- [ ] **MCP Integration**: Live VS Code/GitHub connection
- [ ] **Research Paper**: IEEE submission on architectural compliance

## Research & Prior Art

- **Microsoft CodeReviewer**: [Paper](https://arxiv.org/abs/2203.09095) | [Dataset](https://zenodo.org/records/6900648)
- **Our contribution**: Multi-agent orchestration + real-time codebase awareness + constraint-based prompts + automated compliance validation

## License

MIT License — See [LICENSE](LICENSE)

## Author

**Yuvraj Sharma** — B.Tech 2nd Year
