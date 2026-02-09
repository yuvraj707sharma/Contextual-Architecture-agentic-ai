# Agents Module

Multi-agent framework for the Contextual Architect.

## Architecture

```
agents/
├── __init__.py          # Package exports
├── base.py              # BaseAgent abstract class
├── historian.py         # HistorianAgent ✅
├── architect.py         # ArchitectAgent (TODO)
├── implementer.py       # ImplementerAgent (TODO)
└── reviewer.py          # ReviewerAgent (TODO)
```

## Agent Roles

| Agent | Purpose | Status |
|-------|---------|--------|
| **Historian** | Analyzes PR history, finds patterns | ✅ Built |
| **Architect** | Maps codebase structure, finds utilities | 🔲 TODO |
| **Implementer** | Generates production-grade code | 🔲 TODO |
| **Reviewer** | Security & compliance validation | 🔲 TODO |

## Usage

```python
from agents import HistorianAgent, AgentContext

# Create agent (can work without LLM for testing)
historian = HistorianAgent()

# Create context
context = AgentContext(
    user_request="Add JWT authentication middleware",
    repo_path="/path/to/project",
    language="go",
)

# Run agent
response = await historian.process(context)

# Use output
print(response.summary)
print(response.data["patterns"])
print(response.data["conventions"])
```

## Agent Communication

Agents communicate via `AgentContext` and `AgentResponse`:

```
User Request
    ↓
┌─────────────┐
│  Historian  │ → Finds patterns, conventions
└─────────────┘
    ↓ context
┌─────────────┐  
│  Architect  │ → Maps structure, finds utilities
└─────────────┘
    ↓ context
┌─────────────┐
│ Implementer │ → Generates code with context
└─────────────┘
    ↓ code
┌─────────────┐
│  Reviewer   │ → Validates security & compliance
└─────────────┘
    ↓
Final Code (or rejection → back to Implementer)
```

## LLM Modes

Each agent can run in two modes:

1. **With LLM**: Full reasoning capabilities
2. **Without LLM**: Heuristic fallback (for testing)
