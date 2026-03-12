# MACRO Examples

## 1. Zero Config (Recommended)

```bash
# cd into any project folder, type macro
cd myproject
macro

# Inside the session:
#   ❯ Add a /health endpoint              (builds code)
#   ❯ What does @auth.py do?              (asks about code)
#   ❯ Add JWT auth to @middleware.py      (modifies existing file)
```

## 2. GitHub Repos

```bash
# Clone and analyze any public repo
macro --github tiangolo/fastapi

# Private repos
export GITHUB_TOKEN=ghp_xxxx
macro --github myorg/private-api
```

## 3. Single-Shot Mode

```bash
# Generate a feature
macro "Add user registration with email validation"

# Modify existing file
macro "Add a timeout parameter to @database.py"

# With pseudocode
macro "Add fibonacci ||| 1. Take n 2. Iterative loop 3. Print sequence"

# Dry run (preview only)
macro "Add health check" --dry-run
```

## 4. Multi-Provider

```bash
# Fast agents (Groq) + smart planner (Gemini)
macro --provider groq --planner-provider google

# Fully offline with Ollama
macro --provider ollama --model codellama
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

graph = GraphBuilder("./my-project").build()
analyzer = ImpactAnalyzer(graph)

# Who calls this function?
callers = analyzer.get_callers("auth.py", "login")

# What would break if I change this file?
impact = analyzer.analyze_impact("models/user.py")
print(impact)
```
