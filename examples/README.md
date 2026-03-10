# MACRO Examples

## 1. Interactive Mode (Recommended)

```bash
# Just point at a project — language auto-detected, interactive auto-starts
python -m agents --repo ./your-project

# Analyze any GitHub repo
python -m agents --github tiangolo/fastapi

# Inside the session:
#   ❯ Add a /health endpoint              (builds code)
#   ❯ What does @auth.py do?              (asks about code)
#   ❯ Add JWT auth to @middleware.py      (modifies existing file)
```

## 2. Single-Shot Mode

```bash
# Generate a feature (language auto-detected)
python -m agents "Add user registration with email validation" --repo ./myapp

# Modify existing file
python -m agents "Add a timeout parameter to @database.py" --repo ./myapp

# With pseudocode control
python -m agents "Add fibonacci ||| 1. Take n 2. Iterative loop 3. Print sequence" --repo .

# Dry run (preview only, no file writes)
python -m agents "Add health check" --repo ./myapp --dry-run
```

## 3. GitHub Repos

```bash
# Clone and analyze any public repo
python -m agents --github tiangolo/fastapi

# Private repos (set GITHUB_TOKEN)
export GITHUB_TOKEN=ghp_xxxx
python -m agents --github myorg/private-api
```

## 4. Multi-Provider Setup

```bash
# Fast agents (Groq) + smart planner (Gemini)
python -m agents --repo . --provider groq --planner-provider google

# Fully offline with Ollama
python -m agents --repo . --provider ollama --model codellama
```

## 5. Python API

```python
import asyncio
from agents import Orchestrator
from agents.config import AgentConfig
from agents.llm_client import create_llm_client

async def main():
    llm = create_llm_client(provider="groq")
    config = AgentConfig(llm_provider="groq")
    orchestrator = Orchestrator(llm_client=llm, config=config)

    result = await orchestrator.run(
        user_request="Add a /health endpoint",
        repo_path="./my-project",
        language="python",
    )

    if result.success:
        print(f"Generated: {result.target_file}")
        print(result.generated_code)

asyncio.run(main())
```

## 6. Code Graph Queries

```python
from agents.graph_builder import GraphBuilder
from agents.impact_analyzer import ImpactAnalyzer

# Build graph from any project
graph = GraphBuilder("./my-project").build()
analyzer = ImpactAnalyzer(graph)

# Who calls this function?
callers = analyzer.get_callers("auth.py", "login")

# What would break if I change this file?
impact = analyzer.analyze_impact("models/user.py")
print(impact)  # Shows affected files, functions, and import chains
```
