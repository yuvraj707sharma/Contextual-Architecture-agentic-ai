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

> **WARNING**: If `pip install -e .` fails, you can use `python -m agents` instead of `macro`. Just always run from inside the project folder.

### 1.4 Set an API Key

**Free API key sources:**

| Provider | Free Tier | Get Key At |
|----------|-----------|------------|
| **Google Gemini** (recommended) | 15 req/min | https://aistudio.google.com/apikey |
| **Groq** (recommended) | 30 req/min | https://console.groq.com |
| **OpenAI** | Paid only | https://platform.openai.com |
| **Anthropic** | Paid only | https://console.anthropic.com |

```cmd
:: Windows CMD (no quotes around the value!)
set GROQ_API_KEY=gsk_xxxxxxxxxxxx

:: Or use the setup wizard
macro --setup
```

> After setup, keys are saved permanently.

### 1.5 Verify It Works

Open CMD, `cd` into any project folder, and type:

```cmd
macro
```

You should see the MACRO banner with the bordered input box. Type `exit` to quit.

---

## Step 2: Usage

### The Simplest Way

```cmd
:: Open CMD in your project folder, then just type:
macro
```

That's it. MACRO:
- **Detects the language** from your files (Python, C++, Java, etc.)
- **Enters interactive mode** automatically
- **Uses current directory** as the project

### Other Ways to Launch

```cmd
:: Analyze any GitHub repo (clones automatically)
macro --github tiangolo/fastapi

:: Point at a different folder
macro --repo "C:\path\to\other\project"

:: Single-shot (run one command and exit)
macro "Add login system"

:: Auto-approve all file changes
macro "Add login system" --yes

:: Preview without writing files
macro "Add login system" --dry-run
```

### What You'll See

```
╭──── macro v0.3.0  ·  groq  ·  python ────╮
│  repo  C:\your\project                    │
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
| "What does this project do?" | Chat | Analyzes your code and answers |
| "Is there any security issue?" | Chat | Reviews your code for vulnerabilities |
| "Add user authentication" | Build | Runs the full 12-stage pipeline |
| "Add sort to @data.cpp" | Build | Modifies the specified file |

**Commands:**

| Command | What It Does |
|---------|-------------|
| `help` | Show all commands with examples |
| `status` | Show current config |
| `config` | Show saved config path |
| `clear` | Clear the screen |
| `exit` / `quit` | End the session |

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
  --> Creates: sorting_algorithm.py

❯ Add binary search
  --> Creates: binary_search.cpp (if project is C++)
```

---

## Step 4: Using Pseudocode (Power Feature)

Pseudocode gives MACRO exact instructions on what logic to write.

### In Interactive Mode (using |||)

```
❯ Add factorial ||| 1. Take n from user 2. Use loop not recursion 3. Handle negative input
❯ Add GCD and LCM ||| 1. Take two numbers 2. GCD using Euclidean algorithm 3. LCM = (a*b)/GCD
❯ Add sort to @data.cpp ||| use merge sort, not bubble sort
```

### In Single-Shot Mode (using --pseudocode)

```cmd
macro "Add movie booking" --pseudocode "1. Ask number of tickets 2. Ask seat type 3. Calculate total"
```

---

## Step 5: Multi-Provider (Advanced)

Use different AI models for different tasks:

```cmd
:: Gemini plans (smarter), Groq executes (faster)
macro --planner-provider google
```

---

## Step 6: Understanding the Output

After code generation, MACRO shows proposed changes in a colored diff panel:

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
:: The simplest way — cd into project, type macro
macro

:: Analyze a GitHub repo
macro --github tiangolo/fastapi

:: Single-shot
macro "Add feature"

:: With pseudocode
macro "Add feature" --pseudocode "1. Do X 2. Do Y"

:: Multi-provider
macro --planner-provider google

:: Save config
macro --save-config --provider groq

:: Help
macro --help
```

### Supported Languages (auto-detected)

`python` | `cpp` | `c` | `go` | `typescript` | `javascript` | `java`

### Supported Providers

`groq` | `google` | `openai` | `anthropic` | `deepseek` | `ollama`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `macro` not recognized | Run `pip install -e .` from the project folder |
| `No module named agents` | Use `macro` command, or `cd` into the project folder first |
| `GROQ_API_KEY not found` | Run `macro --save-config --provider groq --api-key YOUR_KEY` |
| `Repository path does not exist` | Check the `--repo` path or just `cd` into the project |
| Creates new file instead of modifying | Use `@filename` in your request |
| Slow response | Groq free tier: 30 req/min. Wait and retry |

---

*MACRO v0.3.0 — Multi-Agent Contextual Repository Orchestrator*
