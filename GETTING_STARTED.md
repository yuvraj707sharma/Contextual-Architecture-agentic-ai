# 🏗️ Contextual Architect — Getting Started Guide

> AI-powered code generation that understands your project's style, conventions, and structure.

---

## 📦 Step 1: Setup (One-Time, ~5 min)

### 1.1 Clone the Project

```cmd
git clone <repo-url>
cd contextual-architect
```

Or copy the `contextual-architect` folder from USB/zip.

### 1.2 Install Python Dependencies

```cmd
pip install -r requirements.txt
```

> **Requires:** Python 3.10+

### 1.3 Get Your API Key

You need at least **one** API key. Pick any provider:

| Provider | Free Tier | Get Key At |
|----------|-----------|------------|
| **Groq** (recommended) | ✅ 30 req/min | https://console.groq.com |
| **Google Gemini** | ✅ 15 req/min | https://aistudio.google.com/apikey |
| **OpenAI** | ❌ Paid | https://platform.openai.com |
| **Anthropic** | ❌ Paid | https://console.anthropic.com |

### 1.4 Save Your Config (One-Time)

**Option A: Using the CLI** (recommended)

```cmd
:: Single provider (Groq only)
python -m agents --save-config --provider groq --api-key gsk_YOUR_KEY_HERE

:: Multi-provider (Groq + Gemini — best quality)
set GROQ_API_KEY=gsk_YOUR_KEY_HERE
set GOOGLE_API_KEY=AIza_YOUR_KEY_HERE
python -m agents --save-config --provider groq --planner-provider google
```

**Option B: Manually create config file**

Create `C:\Users\<YourName>\.contextual-architect\config.json`:

```json
{
  "llm_provider": "groq",
  "llm_api_key": "gsk_YOUR_GROQ_KEY",
  "planner_provider": "google",
  "planner_api_key": "AIza_YOUR_GEMINI_KEY",
  "default_language": "python"
}
```

> After this, you **never** need to set API keys again. They're saved permanently.

### 1.5 Verify It Works

```cmd
python -m agents "Add hello world function" --repo . --lang python
```

You should see `✅ SUCCESS` with generated code.

---

## 🚀 Step 2: Usage

### Mode 1: Interactive Chat (Recommended)

Start a persistent chat session:

```cmd
python -m agents -i --repo "C:\path\to\your\project" --lang python
```

You'll see:

```
  ╔══════════════════════════════════════════════════╗
  ║  🏗️  CONTEXTUAL ARCHITECT                        ║
  ╚══════════════════════════════════════════════════╝

  📁 Repo:     C:\path\to\your\project
  🤖 Provider: groq
  🧠 Planner:  google

  ❯ _
```

Type your requests naturally:

```
  ❯ Add user authentication
  ❯ Add logging to @main.py
  ❯ Add binary search to @sorting.cpp
  ❯ Add factorial ||| 1. Take n 2. Use loop 3. Handle negatives
  ❯ exit
```

**Interactive Commands:**

| Command | What It Does |
|---------|-------------|
| `help` | Show all commands |
| `status` | Show current config |
| `config` | Show saved config path |
| `clear` | Clear the screen |
| `exit` / `quit` | End the session |

### Mode 2: Single-Shot Command

Run one request and exit:

```cmd
:: Python project
python -m agents "Add login system" --repo "C:\my\project" --lang python

:: C++ project
python -m agents "Add binary search algorithm" --repo "C:\DSA\Basic_Mathematics" --lang cpp
```

---

## 📁 Step 3: Working With Your Files

### Referencing Existing Files

Use `@filename` to tell the tool which file to modify:

```
❯ Add booking feature to @Movie_ticket_pricing.py
❯ Fix the bug in @utils/auth.py
❯ Add prime number checker to @Armstrong.cpp
```

This ensures the tool **modifies your file** instead of creating a new one.

### Without File Reference

If you don't mention a file, the tool creates a **new file**:

```
❯ Add sorting algorithm
→ Creates: sorting_algorithm.py (new file)

❯ Add binary search
→ Creates: binary_search.cpp (new file, if --lang cpp)
```

### Changing The Repo

The repo is set when you start the session. To work on a different project:

```cmd
:: Exit current session
❯ exit

:: Start new session with different repo
python -m agents -i --repo "D:\other\project" --lang python
```

---

## 📝 Step 4: Using Pseudocode (Power Feature)

Pseudocode gives the AI **exact instructions** on what logic to write. This is the most powerful feature — it ensures the AI follows YOUR logic, not its own.

### In Interactive Mode (using `|||`)

Type your request, then `|||`, then the pseudocode:

```
❯ Add factorial ||| 1. Take n from user 2. Use loop not recursion 3. Handle negative input
❯ Add GCD and LCM ||| 1. Take two numbers 2. GCD using Euclidean algorithm 3. LCM = (a*b)/GCD
❯ Add sort to @data.cpp ||| use merge sort, not bubble sort
```

### In Single-Shot Mode (using `--pseudocode`)

```cmd
python -m agents "Add movie booking" --repo "C:\project" --lang python --pseudocode "1. Ask number of tickets 2. Ask seat type premium or regular 3. Premium costs extra $5 4. Calculate total 5. Print receipt"
```

### From a File

Create a file `my_plan.txt`:

```
1. Get user age and day of week
2. Base price: $12 for adults, $8 for children
3. Wednesday discount: $2 off
4. Ask number of tickets
5. Ask seat type (premium +$5, regular)
6. Calculate total
7. Print itemized receipt
```

Then:

```cmd
python -m agents "Add booking to @Movie_ticket_pricing.py" --repo "C:\project" --lang python --pseudocode my_plan.txt
```

---

## ⚙️ Step 5: Multi-Provider (Advanced)

Use different AI models for different tasks:

```cmd
:: Gemini plans (smarter), Groq executes (faster)
python -m agents -i --repo "C:\project" --lang python --planner-provider google
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

## 📊 Step 6: Understanding the Output

Every run produces a result like this:

```
======================================================================
  CONTEXTUAL ARCHITECT — RESULT
======================================================================

  ✅ SUCCESS
  📁 Target File:  Movie_ticket_pricing.py
  🔄 Attempts:     1

  📝 Proposed Changes:
     ✅ NEW FILES (auto-approved)         ← Safe, auto-created
     ⚠️  MODIFICATIONS (permission req)  ← Needs your approval
     🚫 NOT MODIFIED (preserved)         ← Your existing files stay safe

  💻 Generated Code Preview:
     [shows the actual code]
```

### Change Types

| Symbol | Meaning |
|--------|---------|
| ✅ `CREATE` | New file — safe, auto-approved |
| ⚠️ `MODIFY` | Changes existing file — needs permission |
| ⛔ `BLOCKED` | Dangerous change detected — won't apply |
| 🚫 `NOT MODIFIED` | Existing file preserved as-is |

### Where Are the Files?

- **Generated code & plan:** `<your-repo>/.contextual-architect/`
- **Your config:** `~/.contextual-architect/config.json`

---

## 🔍 Step 7: Testing & Giving Feedback

### What to Test

1. **Basic requests** — "Add a calculator", "Add factorial function"
2. **File modifications** — "Add feature to @existing_file.py" or @armstrong.cpp
3. **With pseudocode** — Use `|||` in interactive or `--pseudocode` in CLI
4. **Style matching** — Does C++ output use `cout` (not `std::cout`)? Does Python match naming?
5. **Edge cases** — Empty requests, wrong paths, wrong language flag
6. **Code quality** — Does the output compile/run correctly?

### How to Report Issues

For each test, note:

```
Command:    python -m agents "Add feature" --repo ./project --lang python
Expected:   Should modify existing file
Actual:     Created new file instead
Severity:   🟡 Bad UX (not a crash, but wrong behavior)
```

### Feedback Categories

| 🟢 Works | Feature works as expected |
| 🟡 Bad UX | Works but confusing/wrong behavior |
| 🔴 Broken | Crash, error, or security issue |
| 💡 Idea | Feature suggestion or improvement |

---

## 📋 Quick Reference

```cmd
:: Interactive mode (Python)
python -m agents -i --repo "C:\project" --lang python

:: Interactive mode (C++)
python -m agents -i --repo "C:\DSA\Basic_Mathematics" --lang cpp

:: Single-shot
python -m agents "Add feature" --repo "C:\project" --lang python

:: With pseudocode (CLI)
python -m agents "Add feature" --repo "C:\project" --lang python --pseudocode "1. Do X 2. Do Y"

:: With pseudocode (interactive)
:: Inside the ❯ prompt, type:  Add feature ||| 1. Do X 2. Do Y

:: Multi-provider
python -m agents "Add feature" --repo "C:\project" --lang python --planner-provider google

:: Save config
python -m agents --save-config --provider groq --planner-provider google

:: Help
python -m agents --help
```

### Supported Languages

`python` | `cpp` | `c` | `go` | `typescript` | `javascript` | `java`

### Supported Providers

`groq` | `google` | `openai` | `anthropic` | `deepseek` | `ollama`

---

## ❓ Troubleshooting

| Problem | Fix |
|---------|-----|
| `GROQ_API_KEY not found` | Run `--save-config` with `--api-key` flag |
| `Repository path does not exist` | Check the `--repo` path is correct |
| `pip install -e .` fails | Ignore it — use `python -m agents` directly |
| Tool creates new file instead of modifying | Use `@filename` in your request |
| `⛔ BLOCKED: 80% deletion` | The tool protected your file from replacement |
| Slow response | Groq free tier: 30 req/min. Wait and retry |
| C++ uses `std::cout` instead of `cout` | Re-check your project has `using namespace std;` in .cpp files |
| `|||` pseudocode not working | Make sure you're in interactive mode (`-i`) |

---

## 🎯 Real-World Examples (Tested)

### Example 1: C++ — New File

```cmd
python -m agents -i --repo C:\DSA\Basic_Mathematics --lang cpp
```
```
❯ Add factorial function ||| 1. Take n from user 2. Use loop not recursion 3. Handle negative input
```

**Result:** Creates `add_factorial_function.cpp` with:
```cpp
#include<iostream>         // ✅ Matches project style
using namespace std;       // ✅ Detected from your files

long long calculateFactorial(int n) {
    if (n < 0) throw "Error: not defined for negatives";
    long long factorial = 1;
    for (int i = 2; i <= n; i++)   // ✅ Loop, not recursion
        factorial *= i;
    return factorial;
}

int main() {
    int n;
    cout << "Enter a number: ";  // ✅ cout, not std::cout
    cin >> n;
    // ...
}
```

### Example 2: C++ — Modify Existing File

```
❯ Add prime number checker to @Armstrong.cpp
```

**Result:** Shows a diff preview of changes to `Armstrong.cpp`, preserving all existing code.

### Example 3: Python — New File

```cmd
python -m agents "Add calculator with add subtract multiply divide" --repo E:\FUn\Learn_Python --lang python
```

**Result:** Creates `calculator.py` following your project's conventions (naming, style, structure).

---

*Built with ❤️ — Contextual Architect v1.0*
