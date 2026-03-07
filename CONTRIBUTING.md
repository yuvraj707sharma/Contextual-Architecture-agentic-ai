# Contributing to MACRO

Thanks for your interest in contributing! MACRO is open to contributions of all sizes.

## Quick Start

```bash
git clone https://github.com/yuvraj707sharma/Contextual-Architecture-agentic-ai.git
cd contextual-architect
pip install -r requirements.txt
pip install -e ".[dev]"
python -m pytest agents/tests/ -q
```

## Development Setup

**Requirements**: Python 3.10+

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest agents/tests/ -q

# Run linter
ruff check agents/

# Run a specific test file
python -m pytest agents/tests/test_graph_builder.py -v
```

## Project Structure

```
agents/
├── orchestrator.py       # Coordinates 12-stage pipeline
├── historian.py          # Convention detection
├── architect.py          # Structure mapping + file routing
├── planner.py            # Structured planning
├── implementer.py        # Code generation with full context
├── reviewer.py           # Security + linting validation
├── graph_builder.py      # AST-based code relationship graph
├── impact_analyzer.py    # Graph queries for affected files
├── shell_executor.py     # Sandboxed command execution
├── pipeline_report.py    # Pipeline results dashboard
├── safe_writer.py        # Permission-based file writing
└── tests/                # 389 unit tests
```

## How to Contribute

### Bug Reports
Open an issue with:
- What command you ran
- What you expected
- What happened instead
- Your Python version and OS

### Feature Requests
Open an issue describing:
- The problem you want solved
- How you'd use the feature
- Any alternatives you've considered

### Code Changes

1. Fork the repo
2. Create a branch: `git checkout -b feat/your-feature`
3. Make changes
4. Run tests: `python -m pytest agents/tests/ -q`
5. Run linter: `ruff check agents/`
6. Commit with conventional messages: `feat:`, `fix:`, `docs:`, `test:`
7. Open a PR

### Good First Issues

Look for issues labeled `good first issue`. These are specifically chosen to be approachable for new contributors.

## Code Style

- Python 3.10+ features welcome
- Type hints encouraged
- Docstrings for public functions
- Line length: 120 chars
- Linter: `ruff` (config in `pyproject.toml`)

## Testing

Every new feature needs tests. We have 389 tests and aim to keep that number climbing.

```bash
# Run all tests
python -m pytest agents/tests/ -q

# Run with coverage
python -m pytest agents/tests/ --cov=agents --cov-report=term-missing
```

## Architecture

MACRO uses a 12-stage pipeline. Each agent is a separate module with a clear contract:

```
Scanner → Graph → [Historian, Architect, Style, PR Search] → Clarification → Impact → Planner → Alignment → Implementer → Reviewer → TestGen → SafeWriter
```

Key design principles:
- **Agents are independent** — each has a system prompt, takes an `AgentContext`, returns an `AgentResponse`
- **Parallel discovery** — Historian, Architect, Style, and PR Search run concurrently
- **Plan-first** — code is never generated without a structured plan
- **Deterministic where possible** — AST graph gives facts, not LLM guesses

## License

Apache 2.0 — See [LICENSE](LICENSE)
