# MACRO — Getting Started Guide

> Multi-Agent Contextual Repository Orchestrator — AI-powered code generation that understands your project's style, conventions, and structure.
> 
> **12-stage pipeline** · **420 tests** · **7 LLM providers** · **$0 with free APIs**

---

## Step 1: Setup (One-Time, ~5 min)

### 1.1 Get the Project

```bash
git clone https://github.com/yuvraj707sharma/Contextual-Architecture-agentic-ai.git
cd Contextual-Architecture-agentic-ai
```

### 1.2 Install Python

Download Python 3.10+ from https://www.python.org/downloads/

> **IMPORTANT**: Check "Add Python to PATH" during installation.

### 1.3 Install Dependencies

Open Command Prompt (cmd) **inside the project folder**:

```cmd
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

> **WARNING**: If `pip install -e .` fails with a setuptools error, you can skip it and use `python -m agents` instead of `macro`. Just make sure to always run from inside the project folder.

### 1.4 Set an API Key

**Free API key sources:**

| Provider | Free Tier | Get Key At |
|----------|-----------|------------|
| **Google Gemini** (recommended) | 15 req/min | https://aistudio.google.com/apikey |
| **Groq** (recommended) | 30 req/min | https://console.groq.com |
| **OpenAI** | Paid only | https://platform.openai.com |
| **Anthropic** | Paid only | https://console.anthropic.com |

Set your key:

```cmd
:: Windows CMD (no quotes around the value!)
set GROQ_API_KEY=gsk_xxxxxxxxxxxx

:: Or use the interactive setup wizard
python -m agents --setup
```

> After setup, keys are saved permanently. You won't need to set them again.

### 1.5 Verify It Works

```cmd
python -m agents --repo .
```

You should see the MACRO banner with the bordered input box. Type `exit` to quit.

---

## Step 2: Usage

### Interactive Mode (Recommended)

Just point MACRO at any project folder — language is auto-detected, interactive mode auto-starts:

```cmd
:: Python project
python -m agents --repo "C:\path\to\your\project"

:: C++ project
python -m agents --repo "C:\DSA\Basic_Mathematics"

:: Any GitHub repo (clones automatically)
python -m agents --github tiangolo/fastapi
```

You'll see:

```
╭──── macro v0.3.0  ·  groq  ·  python ────╮
│  repo  C:\path\to\your\project            │
│                                           │
│  scan → graph → plan → code → review →    │
│  test → write                             │
│                                           │
│  ask   questions about your code          │
│  build type what you want to build        │
│  help  show all commands                  │
╰───────────────────────────────────────────╯

  your-project                 groq · llama3-70b
  ╭─────────────────────────────────────────╮
  │ ❯ _                                    │
  ╰─────────────────────────────────────────╯
```

**Two modes — auto-detected:**

| You Type | Mode | What Happens |
|----------|------|-------------|
| "What does this project do?" | Chat | Analyzes your code and answers the question |
| "Is there any security issue?" | Chat | Reviews your code for vulnerabilities |
| "Add user authentication" | Build | Runs the full 12-stage pipeline and generates code |
| "Add sort to @data.cpp" | Build | Modifies the specified file |

**Interactive Commands:**

| Command | What It Does |
|---------|-------------|
| `help` | Show all commands with examples |
| `status` | Show current config |
| `config` | Show saved config path |
| `clear` | Clear the screen |
| `exit` / `quit` | End the session |

### Single-Shot Mode

Run one request and exit:

```cmd
python -m agents "Add login system" --repo "C:\my\project"
python -m agents "Add binary search algorithm" --repo "C:\DSA"

:: Auto-approve all changes (skip permission prompts)
python -m agents "Add login system" --repo "C:\my\project" --yes

:: Preview without writing files
python -m agents "Add login system" --repo "C:\my\project" --dry-run
```

### GitHub Repos

```cmd
:: Any public repo — clones and caches automatically
python -m agents --github tiangolo/fastapi

:: Private repos
set GITHUB_TOKEN=ghp_xxxx
python -m agents --github myorg/private-api
```

---

## Step 3: Working With Your Files

### Reference Existing Files with @

Use `@filename` to tell MACRO which file to modify:

```
❯ Add booking feature to @Movie_ticket_pricing.py
❯ Fix the bug in @utils.py
❯ What does @Armstrong.cpp do?
```

This ensures MACRO **modifies your file** instead of creating a new one.

### Without File Reference

If you don't mention a file, MACRO creates a **new file**:

```
❯ Add sorting algorithm
  --> Creates: sorting_algorithm.py (new file)

❯ Add binary search
  --> Creates: binary_search.cpp (if project is C++)
```

---

## Step 4: Using Pseudocode (Power Feature)

Pseudocode gives MACRO exact instructions on what logic to write.

### In Interactive Mode (using |||)

Type your request, then `|||`, then the pseudocode:

```
❯ Add factorial ||| 1. Take n from user 2. Use loop not recursion 3. Handle negative input
❯ Add GCD and LCM ||| 1. Take two numbers 2. GCD using Euclidean algorithm 3. LCM = (a*b)/GCD
❯ Add sort to @data.cpp ||| use merge sort, not bubble sort
```

### In Single-Shot Mode (using --pseudocode)

```cmd
python -m agents "Add movie booking" --repo "C:\project" --pseudocode "1. Ask number of tickets 2. Ask seat type 3. Calculate total 4. Print receipt"
```

### From a File

Create `my_plan.txt`:

```
1. Get user age and day of week
2. Base price: $12 for adults, $8 for children
3. Wednesday discount: $2 off
4. Calculate total
5. Print receipt
```

Then:

```cmd
python -m agents "Add booking to @Movie_ticket_pricing.py" --repo "C:\project" --pseudocode my_plan.txt
```

---

## Step 5: Multi-Provider (Advanced)

Use different AI models for different tasks:

```cmd
:: Gemini plans (smarter), Groq executes (faster)
python -m agents --repo "C:\project" --planner-provider google
```

| Agent | Default Provider | What It Does |
|-------|-----------------|-------------|
| Historian | Groq (fast) | Detects project conventions |
| Architect | Groq (fast) | Maps project structure |
| **Planner** | **Gemini** (smart) | Plans what to build |
| **Implementer** | Groq/Gemini | Writes the actual code |
| Reviewer | Groq (fast) | Validates the output |
| Test Generator | Groq | Creates unit tests |

---

## Step 6: Understanding the Output

Every build run produces a **pipeline dashboard** (like GitHub Actions):

```
┌── 🔄 ✅ PIPELINE PASSED in 2340ms ──────────────────────┐
│ Request: Add JWT authentication to login endpoint        │
│ Target:  services/auth.py                                │
│ Complexity: medium                                       │
└──────────────────────────────────────────────────────────┘

┌── 📊 Summary ───────────────────────────────────────────┐
│ 📋 What was done:                                        │
│   📚 Historian: Found existing session-based auth        │
│   🏗️ Architect: Target: services/auth.py (MODIFY)       │
│   📝 Planner: Add JWT auth with token refresh            │
│ 💡 Why these decisions:                                  │
│   • Matched project style: snake_case naming             │
│   • Target file: services/auth.py (action: MODIFY)       │
└──────────────────────────────────────────────────────────┘
```

After code generation, MACRO shows proposed changes in a colored diff panel and asks for approval:

```
╭──── Proposed Changes ─────────────────────╮
│  ✓ new_file.py (new — auto-ok)            │
│                                           │
│  [1] existing.py (medium risk)            │
│      + from auth.middleware import jwt     │
│      + app.add_middleware(jwt)             │
│                                           │
│  Options: [a]pprove  [1,2,3]  [n]one      │
╰───────────────────────────────────────────╯
```

---

## Quick Reference

```cmd
:: Just point at a project (auto-detect + interactive)
python -m agents --repo "C:\project"

:: GitHub repo
python -m agents --github tiangolo/fastapi

:: Single-shot
python -m agents "Add feature" --repo "C:\project"

:: With pseudocode (CLI)
python -m agents "Add feature" --repo "C:\project" --pseudocode "1. Do X 2. Do Y"

:: With pseudocode (interactive)
:: Inside the ❯ prompt, type:  Add feature ||| 1. Do X 2. Do Y

:: Multi-provider
python -m agents "Add feature" --repo "C:\project" --planner-provider google

:: Save config
python -m agents --save-config --provider groq --planner-provider google

:: Help
python -m agents --help

:: Auto-approve all changes
python -m agents "Add feature" --repo "C:\project" --yes

:: Preview without writing
python -m agents "Add feature" --repo "C:\project" --dry-run
```

### Supported Languages (auto-detected)

`python` | `cpp` | `c` | `go` | `typescript` | `javascript` | `java`

### Supported Providers

`groq` | `google` | `openai` | `anthropic` | `deepseek` | `ollama`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `macro` not recognized | Run `pip install -e .` from the project folder, or use `python -m agents` |
| `No module named agents` | You're not in the project folder. `cd` into it first |
| `GROQ_API_KEY not found` | Run `python -m agents --save-config --provider groq --api-key YOUR_KEY` |
| `Repository path does not exist` | Check the `--repo` path is correct |
| Tool creates new file instead of modifying | Use `@filename` in your request |
| `BLOCKED: 80% deletion` | The tool protected your file from replacement |
| Slow response | Groq free tier: 30 req/min. Wait and retry |
| `UnicodeEncodeError` | Use Windows Terminal instead of cmd, or update to latest version |

---

*MACRO v0.3.0 — Multi-Agent Contextual Repository Orchestrator*
