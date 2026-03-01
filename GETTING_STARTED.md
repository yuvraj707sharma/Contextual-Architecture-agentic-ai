# MACRO -- Getting Started Guide

> Multi-Agent Contextual Repository Orchestrator -- AI-powered code generation that understands your project's style, conventions, and structure.

---

## Step 1: Setup (One-Time, ~5 min)

### 1.1 Get the Project

Download the zip file and extract it. You should have a folder like:
```
Downloads\Contextual-Architecture-agentic-ai-main\Contextual-Architecture-agentic-ai-main\
```

> NOTE: GitHub zips create a double-nested folder. Make sure you're inside the INNER folder (the one that contains `requirements.txt`, `agents/`, `README.md`).

### 1.2 Install Python

Download Python 3.10+ from https://www.python.org/downloads/

> IMPORTANT: Check "Add Python to PATH" during installation.

### 1.3 Install Dependencies

Open Command Prompt (cmd) **inside the project folder** (right-click the folder > "Open in Terminal", or use cd):

```cmd
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install -e .
```

> CAUTION: Common mistakes:
> - The command is `pip install -r requirements.txt` (with `-r` flag and an **s** in requirement**s**)
> - Do NOT type `pip install requirements.txt` (missing -r) or `pip install requirement.txt` (missing -r AND missing s)
> - You must be inside the folder that contains `requirements.txt`. If you get "No such file", type `dir` to check you can see `requirements.txt` in the listing.

> WARNING: If `pip install -e .` fails with a setuptools error, you can skip it and use `python -m agents` instead of `macro`. Just make sure to always run from inside the project folder.

After `pip install -e .` succeeds, the `macro` command works from **anywhere** on your system.

### 1.4 Run the Setup Wizard

```cmd
macro --setup
```

This will:
- Check your system (Python version, dependencies)
- Ask which API provider you want (Gemini and Groq are FREE)
- Test your API key works
- Optionally configure a second provider for smarter planning
- Save everything to config

> TIP: If you just want a quick setup without the wizard:
> ```cmd
> macro --save-config --provider google --api-key YOUR_KEY_HERE
> ```

**Free API key sources:**

| Provider | Free Tier | Get Key At |
|----------|-----------|------------|
| **Google Gemini** (recommended) | 15 req/min | https://aistudio.google.com/apikey |
| **Groq** (recommended) | 30 req/min | https://console.groq.com |
| **OpenAI** | Paid only | https://platform.openai.com |
| **Anthropic** | Paid only | https://console.anthropic.com |
```

> After this, you never need to set API keys again. They're saved permanently.

### 1.6 Verify It Works

```cmd
macro -i --repo . --lang python
```

You should see the MACRO banner with the config section. Type `exit` to quit.

---

## Step 2: Usage

### Interactive Mode (Recommended)

Start a chat session pointed at any folder on your PC:

```cmd
:: Python project
macro -i --repo "C:\path\to\your\project" --lang python

:: C++ project
macro -i --repo "C:\DSA\Basic_Mathematics" --lang cpp

:: Java project
macro -i --repo "D:\Projects\MyApp" --lang java
```

You'll see:

```
      +-------------+
      |  MACRO      |  Multi-Agent Contextual Repository Orchestrator
      +-------------+

  > Repo:     C:\path\to\your\project
  > Language: python
  > Provider: groq

  [?] Chat: Ask questions about your code
  [+] Build: Type what you want to build
  [!] Help:  Type help for all commands

  > _
```

**Two modes -- auto-detected:**

| You Type | Mode | What Happens |
|----------|------|-------------|
| "What does this project do?" | Chat | Analyzes your code and answers the question |
| "Is there any security issue?" | Chat | Reviews your code for vulnerabilities |
| "Add user authentication" | Build | Runs the full 9-agent pipeline and generates code |
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
macro "Add login system" --repo "C:\my\project" --lang python
macro "Add binary search algorithm" --repo "C:\DSA" --lang cpp
```

---

## Step 3: Working With Your Files

### Reference Existing Files with @

Use `@filename` to tell MACRO which file to modify:

```
> Add booking feature to @Movie_ticket_pricing.py
> Fix the bug in @utils.py
> What does @Armstrong.cpp do?
```

This ensures MACRO **modifies your file** instead of creating a new one.

### Without File Reference

If you don't mention a file, MACRO creates a **new file**:

```
> Add sorting algorithm
  --> Creates: sorting_algorithm.py (new file)

> Add binary search
  --> Creates: binary_search.cpp (new file, if --lang cpp)
```

---

## Step 4: Using Pseudocode (Power Feature)

Pseudocode gives MACRO exact instructions on what logic to write.

### In Interactive Mode (using |||)

Type your request, then `|||`, then the pseudocode:

```
> Add factorial ||| 1. Take n from user 2. Use loop not recursion 3. Handle negative input
> Add GCD and LCM ||| 1. Take two numbers 2. GCD using Euclidean algorithm 3. LCM = (a*b)/GCD
> Add sort to @data.cpp ||| use merge sort, not bubble sort
```

### In Single-Shot Mode (using --pseudocode)

```cmd
macro "Add movie booking" --repo "C:\project" --lang python --pseudocode "1. Ask number of tickets 2. Ask seat type 3. Calculate total 4. Print receipt"
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
macro "Add booking to @Movie_ticket_pricing.py" --repo "C:\project" --lang python --pseudocode my_plan.txt
```

---

## Step 5: Multi-Provider (Advanced)

Use different AI models for different tasks:

```cmd
:: Gemini plans (smarter), Groq executes (faster)
macro -i --repo "C:\project" --lang python --planner-provider google
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

Every build run produces a result like this:

```
======================================================================
  MACRO -- RESULT
======================================================================

  SUCCESS
  > Target File:  Movie_ticket_pricing.py
  > Attempts:     1

  > Agent Summaries:
     [historian] 2 patterns found. 4 conventions detected.
     [planner]   3 acceptance criteria defined
     [reviewer]  Passed: 0 errors, 0 warnings

  Proposed Changes:
     CREATE:  new_file.py (auto-approved)
     MODIFY:  existing.py (needs your OK)
     BLOCKED: dangerous_change.py (rejected)
```

### Change Types

| Symbol | Meaning |
|--------|---------|
| `CREATE` | New file -- safe, auto-approved |
| `MODIFY` | Changes existing file -- needs permission |
| `BLOCKED` | Dangerous change detected -- won't apply |
| `NOT MODIFIED` | Existing file preserved as-is |

### Where Are the Files?

- **Generated code & plan:** `<your-repo>/.contextual-architect/`
- **Your config:** `~/.contextual-architect/config.json`

---

## Quick Reference

```cmd
:: Interactive mode (Python)
macro -i --repo "C:\project" --lang python

:: Interactive mode (C++)
macro -i --repo "C:\DSA\Basic_Mathematics" --lang cpp

:: Single-shot
macro "Add feature" --repo "C:\project" --lang python

:: With pseudocode (CLI)
macro "Add feature" --repo "C:\project" --lang python --pseudocode "1. Do X 2. Do Y"

:: With pseudocode (interactive)
:: Inside the > prompt, type:  Add feature ||| 1. Do X 2. Do Y

:: Multi-provider
macro "Add feature" --repo "C:\project" --lang python --planner-provider google

:: Save config
macro --save-config --provider groq --planner-provider google

:: Help
macro --help
```

### Supported Languages

`python` | `cpp` | `c` | `go` | `typescript` | `javascript` | `java`

### Supported Providers

`groq` | `google` | `openai` | `anthropic` | `deepseek` | `ollama`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `macro` not recognized | Run `pip install -e .` from the project folder |
| `No module named agents` | You're not in the project folder. Use `macro` command instead |
| `GROQ_API_KEY not found` | Run `macro --save-config --provider groq --api-key YOUR_KEY` |
| `Repository path does not exist` | Check the `--repo` path is correct |
| Tool creates new file instead of modifying | Use `@filename` in your request |
| `BLOCKED: 80% deletion` | The tool protected your file from replacement |
| Slow response | Groq free tier: 30 req/min. Wait and retry |
| `UnicodeEncodeError` | Use Windows Terminal instead of cmd, or update to latest version |

---

## Testing & Giving Feedback

### What to Test

1. **Chat mode** -- "What does this project do?", "Find bugs in @file.py"
2. **Build mode** -- "Add a calculator", "Add factorial function"
3. **File modifications** -- "Add feature to @existing_file.py"
4. **With pseudocode** -- Use `|||` in interactive or `--pseudocode` in CLI
5. **Style matching** -- Does C++ output use `cout` (not `std::cout`)? Does Python match naming?
6. **Code quality** -- Does the output compile/run correctly?

### How to Report Issues

For each test, note:

```
Command:    macro -i --repo "C:\project" --lang python
Request:    Add login system
Expected:   Should create login_system.py
Actual:     Created feature.py instead
Severity:   Bad UX (not a crash, but wrong behavior)
```

### Feedback Categories

| Category | Meaning |
|----------|---------|
| Works | Feature works as expected |
| Bad UX | Works but confusing/wrong behavior |
| Broken | Crash, error, or security issue |
| Idea | Feature suggestion or improvement |

---

*MACRO v0.1.0 -- Multi-Agent Contextual Repository Orchestrator*
