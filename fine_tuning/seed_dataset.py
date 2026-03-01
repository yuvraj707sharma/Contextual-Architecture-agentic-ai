"""
Hand-crafted seed dataset from real MACRO development sessions.

These are actual debugging, implementation, and reasoning examples
from building MACRO. Each example teaches the model a specific
skill needed for the pipeline:

- Bug diagnosis and fixing
- Feature implementation with planning
- Architecture trade-off reasoning
- Security review patterns
- Cross-platform compatibility

These examples are HIGH QUALITY because they come from real
development, not synthetic generation.

Usage:
    python seed_dataset.py --output data/seed_train.jsonl
"""

import json
import sys
from pathlib import Path


SEED_EXAMPLES = [
    # ── Bug Fix: API key masking broke config reload ──────────
    {
        "messages": [
            {
                "role": "system",
                "content": "You are an expert debugging agent within the MACRO pipeline. When a user reports a bug, you diagnose the root cause, explain the fix, and provide corrected code that follows the project's conventions."
            },
            {
                "role": "user",
                "content": "My friend's Gemini API key gets corrupted when saved. After running macro --save-config, the key in config.json shows as 'AIza****5678' instead of the full key. When he tries to use MACRO next time, the API call fails because it's sending the masked key."
            },
            {
                "role": "assistant",
                "content": """## Root Cause

The `save_to_file()` method in `config.py` is masking the API key before saving it to disk. The masking logic was designed for display purposes (logging, CLI output) but was accidentally applied during file serialization.

## The Bug

```python
# config.py - save_to_file()
def save_to_file(self, path):
    data = self.to_dict()
    # BUG: This masks the key BEFORE saving
    if data.get('llm_api_key'):
        key = data['llm_api_key']
        data['llm_api_key'] = key[:4] + '****' + key[-4:]
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
```

When the config is loaded next time, `llm_api_key` contains `AIza****5678` — which is not a valid API key.

## Fix

Remove the masking from `save_to_file()`. Masking should ONLY happen in display/logging code, never in serialization:

```python
def save_to_file(self, path):
    data = self.to_dict()
    # Save the REAL key - masking is only for display
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    # Set file permissions (Unix only)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
```

## Security Note

The raw API key in the config file is protected by file permissions (chmod 600 on Unix). On Windows, we should warn the user that the key is stored in plaintext."""
            }
        ]
    },
    
    # ── Bug Fix: Emoji crashes on Windows cmd.exe ─────────────
    {
        "messages": [
            {
                "role": "system",
                "content": "You are an expert debugging agent within the MACRO pipeline. When a user reports a bug, you diagnose the root cause, explain the fix, and provide corrected code that follows the project's conventions."
            },
            {
                "role": "user",
                "content": "MACRO crashes on Windows Command Prompt with UnicodeEncodeError when starting interactive mode. The error points to the banner printing code that uses emoji characters like rocket, fire, and checkmark symbols."
            },
            {
                "role": "assistant",
                "content": """## Root Cause

Windows Command Prompt (cmd.exe) defaults to the cp1252 encoding, which cannot render Unicode emoji characters. When Python tries to print emoji (U+1F680 rocket, U+2714 checkmark, etc.), it raises `UnicodeEncodeError: 'charmap' codec can't encode character`.

## Fix Strategy

Replace ALL emoji with ASCII equivalents throughout the codebase. The rule: if it's not in the ASCII printable range (32-126), don't use it in terminal output.

| Before (crashes) | After (safe) |
|--|--|
| `🚀 Starting pipeline` | `[>] Starting pipeline` |
| `✅ Validation passed` | `[OK] Validation passed` |
| `❌ Error occurred` | `[X] Error occurred` |
| `⚠️ Warning` | `[!] Warning` |
| `❯` (prompt) | `>` (prompt) |

## Code Changes

```python
# interactive.py - Replace emoji in 14 locations
# Before:
print("🚀 Starting parallel discovery...")
# After:
print("[>] Starting parallel discovery...")

# For the banner, use encoding detection:
def _can_render_unicode():
    try:
        test = "╔═╗║"
        test.encode(sys.stdout.encoding or "utf-8")
        return True
    except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
        return False
```

## Key Principle

Terminal output should NEVER use characters outside the ASCII range without first checking `sys.stdout.encoding`. The safe approach is ASCII-first with optional Unicode upgrade when the terminal supports it."""
            }
        ]
    },
    
    # ── Bug Fix: Environment variable layering ────────────────
    {
        "messages": [
            {
                "role": "system",
                "content": "You are an expert debugging agent within the MACRO pipeline. When a user reports a bug, you diagnose the root cause, explain the fix, and provide corrected code that follows the project's conventions."
            },
            {
                "role": "user",
                "content": "When I explicitly set CA_LLM_PROVIDER=mock in my environment, the load_user_config() method doesn't recognize it because 'mock' happens to be the default value. The code compares env_val != default_val, so setting the default explicitly gets ignored."
            },
            {
                "role": "assistant",
                "content": """## Root Cause

The `load_user_config()` method determines if an environment variable was "explicitly set" by comparing its value against the default. This is fundamentally flawed:

```python
# BUGGY: comparing by value
env_val = os.environ.get(key, default_val)
if env_val != default_val:  # BUG: misses explicit-default-set
    config[field] = env_val
```

If the user explicitly sets `CA_LLM_PROVIDER=mock` and "mock" is the default, the code thinks nothing changed.

## Fix

Check for the *presence* of the environment variable, not its *value*:

```python
# FIXED: check presence, not value
env_val = os.environ.get(key)
if env_val is not None:  # Variable exists = user set it
    config[field] = env_val
```

This correctly handles:
- `CA_LLM_PROVIDER=mock` → recognized (env var exists)
- No env var set → uses file config or default
- `CA_LLM_PROVIDER=groq` → recognized (different from default)

## General Principle

When layering config sources (defaults < file < env < CLI), check for *existence* at each layer, not *difference from default*. The user might intentionally override a higher-priority source with a value that happens to match a lower-priority default."""
            }
        ]
    },
    
    # ── Feature: Setup Wizard ─────────────────────────────────
    {
        "messages": [
            {
                "role": "system",
                "content": "You are a code implementation agent within the MACRO pipeline. When a user requests a feature, you plan the implementation, consider the project's architecture and conventions, and produce production-grade code with proper error handling."
            },
            {
                "role": "user",
                "content": "Create an interactive setup wizard for MACRO that guides first-time users through selecting an LLM provider, entering their API key, testing the connection, and saving the config. It should support multi-provider setups (fast provider for discovery agents, smart provider for planning). Run with `macro --setup`."
            },
            {
                "role": "assistant",
                "content": """## Plan

1. Create `agents/setup_wizard.py` with `run_setup()` function
2. Add `--setup` flag to `__main__.py` argument parser
3. Setup wizard flow: system checks → provider selection → API key → test → multi-provider option → save

## Implementation

The wizard must:
- Use only ASCII characters (Windows cmd.exe compatibility)
- Auto-detect existing config and offer to update
- Test API keys with a live call before saving
- Support 6 providers: Groq, Google Gemini, OpenAI, Anthropic, DeepSeek, Ollama
- Recommend free providers (Groq, Gemini) for first-time users

```python
# agents/setup_wizard.py

import sys
import os
from pathlib import Path
from .config import AgentConfig

def run_setup():
    print()
    print("  MACRO Setup Wizard")
    print("  " + "=" * 40)
    
    # Step 1: System checks
    check_python_version()
    check_dependencies()
    
    # Step 2: Provider selection with recommendations
    providers = {
        "1": ("groq", "Groq (FREE - 30 req/min)"),
        "2": ("google", "Google Gemini (FREE - 15 req/min)"),
        "3": ("deepseek", "DeepSeek ($0.14/1M tokens)"),
        "4": ("openai", "OpenAI GPT-4o (paid)"),
        "5": ("anthropic", "Anthropic Claude (paid)"),
        "6": ("ollama", "Ollama (local, free)"),
    }
    
    print("\\n  Select your LLM provider:")
    print("  [*] = recommended for getting started\\n")
    for key, (_, name) in providers.items():
        prefix = "  [*]" if key in ("1", "2") else "     "
        print(f"  {prefix} {key}. {name}")
    
    choice = input("\\n  Enter choice (1-6): ").strip()
    provider, _ = providers.get(choice, ("groq", ""))
    
    # Step 3: API key input + validation
    api_key = input(f"\\n  Enter your {provider} API key: ").strip()
    
    # Step 4: Test connection
    print(f"  Testing connection to {provider}...", end=" ")
    if test_connection(provider, api_key):
        print("OK")
    else:
        print("FAILED")
        return
    
    # Step 5: Optional multi-provider
    print("\\n  [Optional] Use a smarter model for planning?")
    print("  This routes planning to a better model while keeping")
    print("  fast agents on the cheap provider.")
    
    # Step 6: Save
    config = AgentConfig(llm_provider=provider, llm_api_key=api_key)
    config.save_to_file()
    print("\\n  Config saved! Run: macro -i --repo .")
```

## Key Design Decisions

- ASCII-only output: no emoji, no Unicode box chars
- Provider recommendations: highlight free tiers first
- Live API test: validates key before saving (prevents broken configs)
- Multi-provider is optional: beginners skip it, power users enable it"""
            }
        ]
    },
    
    # ── Feature: Trace Logging for Distillation ───────────────
    {
        "messages": [
            {
                "role": "system",
                "content": "You are a code implementation agent within the MACRO pipeline. When a user requests a feature, you plan the implementation, consider the project's architecture and conventions, and produce production-grade code with proper error handling."
            },
            {
                "role": "user",
                "content": "Add trace logging to the orchestrator that saves every agent's input/output as JSONL for future model distillation. It should log to ~/.contextual-architect/traces/YYYY-MM-DD.jsonl, one line per pipeline run. It must NEVER crash the pipeline — all trace calls should be wrapped in try/except."
            },
            {
                "role": "assistant",
                "content": """## Plan

Create `agents/trace_logger.py` with a `TraceLogger` class, then wire it into `orchestrator.py` at 6 points:
1. Pipeline start (metadata)
2. Discovery agents (historian, architect, style)
3. Planner output
4. Implementer (in retry loop)
5. Reviewer (in retry loop)
6. Final result save

## Implementation

```python
# agents/trace_logger.py
import json, os, time
from datetime import datetime, timezone
from pathlib import Path

class TraceLogger:
    def __init__(self):
        self._traces = []
        self._run_id = f"{int(time.time())}_{os.getpid()}"
        self._start_time = time.perf_counter()
        self._metadata = {}
    
    def set_metadata(self, user_request, repo_path, language, provider=""):
        repo_name = Path(repo_path).name  # Privacy: no full path
        self._metadata = {
            "run_id": self._run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_request": user_request,
            "repo_name": repo_name,
            "language": language,
            "provider": provider,
        }
    
    def log_agent(self, agent, input_summary, output_summary, 
                  output_data=None, success=True, attempt=1):
        data = _truncate_data(output_data) if output_data else {}
        self._traces.append({
            "agent": agent, "attempt": attempt, "success": success,
            "input_summary": input_summary[:500],
            "output_summary": output_summary[:500],
            "output_data": data,
        })
    
    def save(self):
        try:
            traces_dir = Path.home() / ".contextual-architect" / "traces"
            traces_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            trace_file = traces_dir / f"{date_str}.jsonl"
            record = {**self._metadata, "agent_traces": self._traces}
            with open(trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\\n")
        except Exception:
            pass  # NEVER break the pipeline
```

## Orchestrator Integration

Every trace call is wrapped in `try/except`:

```python
# orchestrator.py - run() method
tracer = TraceLogger()
try:
    tracer.set_metadata(user_request, repo_path, language, ...)
except Exception:
    pass

# After each agent:
try:
    tracer.log_agent("historian", ..., historian_response.data, ...)
except Exception:
    pass

# At the end:
try:
    tracer.log_result(success=result.success, attempts=result.attempts)
    tracer.save()
except Exception:
    pass  # Never break the pipeline
```

## Key Design Decisions

- **Privacy**: Only repo name in traces, never full path or API keys
- **Truncation**: Large strings capped at 2000 chars to keep traces manageable
- **One file per day**: `2026-03-01.jsonl` keeps files at reasonable size
- **Append-only**: Multiple runs accumulate in the same daily file
- **Silent failure**: Every trace operation is wrapped, pipeline never breaks"""
            }
        ]
    },
    
    # ── Architecture: License Choice ──────────────────────────
    {
        "messages": [
            {
                "role": "system",
                "content": "You are an architecture reasoning agent within the MACRO pipeline. When asked about design decisions, you analyze trade-offs, consider the project's constraints, and provide clear recommendations with justification."
            },
            {
                "role": "user",
                "content": "Should MACRO use MIT, Apache 2.0, or GPL license? I want to prevent people from just copying the code and selling it as their own, but I also want it to be open source. The project has a patent filed."
            },
            {
                "role": "assistant",
                "content": """## License Comparison for MACRO

| License | Can Fork? | Must Credit You? | Must Share Changes? | Patent Protection |
|--|--|--|--|--|
| MIT | Yes | Yes (name only) | No | None |
| Apache 2.0 | Yes | Yes + change notices | No | Yes — patent grant |
| GPL v3 | Yes | Yes | Yes (copyleft) | Yes |
| AGPL v3 | Yes | Yes | Yes (even SaaS) | Yes |

## Recommendation: Apache 2.0

1. **Patent protection**: Apache 2.0 includes an explicit patent grant. Since you have a provisional patent, this protects you — anyone who uses the code gets a patent license, but if they sue you for patent infringement, their license terminates automatically.

2. **Attribution requirement**: Anyone who forks MACRO must keep your copyright notice AND list what they changed. With MIT, they just need your name.

3. **Not copyleft**: Unlike GPL, Apache 2.0 lets enterprises use MACRO without being forced to open-source their entire codebase. This is critical for your Enterprise tier.

4. **Industry standard**: Same license as TensorFlow, Kubernetes, Gemini CLI, Android. Enterprises trust it.

## Why NOT GPL

GPL would force anyone who uses MACRO to open-source their modifications. This sounds protective but actually hurts adoption — enterprises won't touch GPL code in commercial products. Your target market (banks, defense, healthcare) would be unable to use MACRO.

## Why NOT MIT

MIT offers zero patent protection and minimal attribution requirements. Someone could rebrand MACRO, add a UI, and sell it without mentioning you. Apache 2.0 closes this gap."""
            }
        ]
    },
    
    # ── Architecture: Banner Encoding Detection ───────────────
    {
        "messages": [
            {
                "role": "system",
                "content": "You are an architecture reasoning agent within the MACRO pipeline. When asked about design decisions, you analyze trade-offs, consider the project's constraints, and provide clear recommendations with justification."
            },
            {
                "role": "user",
                "content": "The CLI banner uses Unicode box-drawing characters that crash on Windows cmd.exe. What's the best approach to handle this?"
            },
            {
                "role": "assistant",
                "content": """## The Problem

Windows cmd.exe defaults to cp1252 encoding, which cannot render Unicode box-drawing chars (U+2500 ─, U+2502 │, U+256D ╭, etc.). PowerShell and Windows Terminal handle them fine, but cmd.exe crashes with UnicodeEncodeError.

## Options Analyzed

| Approach | Dependency | Win cmd Safe? | Looks Good? |
|--|--|--|--|
| Raw ASCII only (`+--+`, `|`) | None | Yes | Basic |
| Encoding detection + fallback | None | Yes | Good |
| `colorama` library | 1 package | Yes | Good + colors |
| `rich` library | 1 package | Yes | Excellent |

## Recommendation: Encoding Detection + ASCII Fallback

No new dependencies, works everywhere:

```python
def _can_render_unicode():
    try:
        "╭─╮│╰╯".encode(sys.stdout.encoding or "utf-8")
        return True
    except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
        return False
```

Then use ASCII art for the logo (universally safe via raw strings):

```python
logo = r\"""
  __  __    _    ____ ____   ___
 |  \\/  |  / \\  / ___|  _ \\ / _ \\
 | |\\/| | / _ \\| |   | |_) | | | |
 | |  | |/ ___ \\ |___|  _ <| |_| |
 |_|  |_/_/   \\_\\____|_| \\_\\\\___/
\"""
```

And for config box: test encoding first, fall back to `+--+` on legacy terminals.

## Why Not rich/colorama

Adding dependencies for a banner is overkill. MACRO already uses ANSI escape codes for colors (which work on all modern terminals including cmd.exe with ANSI support). The banner character issue is specifically about encoding, not colors."""
            }
        ]
    },
    
    # ── Security Review: Config File Permissions ──────────────
    {
        "messages": [
            {
                "role": "system",
                "content": "You are a code review agent within the MACRO pipeline. You identify bugs, security vulnerabilities (CWE denylist), performance issues, and convention violations. You provide specific fixes with corrected code."
            },
            {
                "role": "user",
                "content": "Review the security of how MACRO stores API keys in the config file. The save_to_file() method uses chmod 0o600 on Unix, but on Windows the except OSError: pass means the config file has no extra protection."
            },
            {
                "role": "assistant",
                "content": """## Security Review: API Key Storage

### Finding 1: Windows plaintext API keys (CWE-312: Cleartext Storage)

**Severity**: Medium

On Unix, `os.chmod(path, 0o600)` restricts the config file to owner-only access. On Windows, this call raises `OSError` and is silently caught, leaving the API key readable by any process running as the same user.

**Fix**: Add a warning on Windows so users are informed:

```python
import warnings

def save_to_file(self, path):
    # ... save logic ...
    try:
        os.chmod(path, 0o600)
    except OSError:
        if os.name == 'nt':
            warnings.warn(
                f"API keys saved in plaintext at {path}. "
                "Windows does not support Unix file permissions. "
                "Consider using Windows EFS or manually restricting "
                "access via file properties.",
                UserWarning,
                stacklevel=2,
            )
```

### Finding 2: Key not encrypted at rest

The API key is stored as plain JSON. For production use, consider:
- Windows: DPAPI via `win32crypt.CryptProtectData()`
- macOS: Keychain via `keyring` library
- Linux: Secret Service via `keyring` library

However, for the current project stage, plaintext with file permissions is acceptable (same approach as AWS CLI, gcloud CLI, and most developer tools).

### Finding 3: No key in logs

Verified: the logger and trace_logger do NOT log the API key. The trace_logger only logs the provider name. This is correct.

### Verdict: Acceptable for current stage, with Windows warning added."""
            }
        ]
    },
    
    # ── Reasoning: Multi-Provider Routing ─────────────────────
    {
        "messages": [
            {
                "role": "system",
                "content": "You are a reasoning agent within the MACRO multi-agent pipeline. You think through problems step by step, considering conventions, architecture, security, and the project's specific patterns."
            },
            {
                "role": "user",
                "content": "How should the orchestrator route agents to different LLM providers? Discovery agents (Historian, Architect, Style) don't need strong reasoning, but the Planner and Implementer need high-quality output."
            },
            {
                "role": "assistant",
                "content": """## Step-by-Step Reasoning

### Step 1: Classify agents by intelligence requirement

| Agent | Task | Needs Strong Reasoning? | Best Provider |
|--|--|--|--|
| Historian | Scan conventions | No — pattern matching | Fast/cheap |
| Architect | Map structure | No — analysis | Fast/cheap |
| Style Analyzer | Extract patterns | No — regex + stats | No LLM needed |
| PR Searcher | Search PRs | No — keyword search | No LLM needed |
| Planner | Create structured plan | YES — complex reasoning | Smart/expensive |
| Alignment | Validate plan | Moderate | Smart/expensive |
| Implementer | Generate code | YES — code generation | Smart/expensive |
| Reviewer | Validate code | Moderate — rule-based + LLM | Fast/cheap |
| Test Generator | Write tests | YES — code generation | Smart/expensive |

### Step 2: Optimal routing strategy

```
Discovery agents → Groq (free, fast, llama-3.3-70b)
Planning agents  → Google Gemini 2.5 Pro (smart, free tier)
Code generation  → Google Gemini 2.5 Pro OR Claude (best quality)
```

### Step 3: Implementation in AgentConfig

The config needs `planner_provider` and `implementer_provider` fields:

```python
@dataclass
class AgentConfig:
    llm_provider: str = "groq"           # Default for fast agents
    planner_provider: str = ""           # Override for planner
    implementer_provider: str = ""       # Override for implementer
```

The orchestrator creates separate LLM clients:
- `self.planner = PlannerAgent(planner_client)`
- `self.implementer = ImplementerAgent(implementer_client)`
- `self.historian = HistorianAgent(default_client)`

### Step 4: Cost impact

With Groq (free) + Gemini (free):
- Total cost per task: $0.00
- Discovery: 0 cost (Groq free tier)
- Planning + Implementation: 0 cost (Gemini free tier)
- Total monthly cost for 50 tasks: $0.00

This makes MACRO the cheapest coding agent in the market while maintaining high output quality for the critical planning and implementation stages."""
            }
        ]
    },
    
    # ── Reasoning: Fine-Tuning Strategy ───────────────────────
    {
        "messages": [
            {
                "role": "system",
                "content": "You are a reasoning agent within the MACRO multi-agent pipeline. You think through problems step by step, considering conventions, architecture, security, and the project's specific patterns."
            },
            {
                "role": "user",
                "content": "I want to fine-tune a model for MACRO using distillation. Should I use public code datasets from HuggingFace, or generate my own data by running the pipeline?"
            },
            {
                "role": "assistant",
                "content": """## Step-by-Step Analysis

### Step 1: What does the model need to learn?

The distilled model doesn't need to learn general coding (it already knows that from pre-training). It needs to learn:
1. MACRO's inter-agent communication protocol
2. How to produce structured plans in MACRO's format
3. How to reason about conventions, architecture, and security
4. The specific JSON schemas the pipeline uses

### Step 2: Evaluate data sources

| Source | Quality | Relevance to MACRO | Volume |
|--|--|--|--|
| Public datasets (CodeAlpaca, etc.) | Mixed — many are GPT-3.5 generated | Low — generic code, no planning | High (20K-200K) |
| MACRO pipeline traces | High — real pipeline data | Perfect — exact format | Low (50-500) |
| Teacher distillation (GPT-4o/Claude on YOUR tasks) | High | High | Medium (200-1000) |
| Our development conversations | Very high — real debugging | High — teaches reasoning | Low (10-50 examples) |

### Step 3: The quality problem with public datasets

Most public code datasets have issues:
- CodeAlpaca-20K: Generated by GPT-3.5, many examples are shallow
- Glaive-Code-Assistant: Synthetic, repetitive patterns
- WizardLM-Evol-Instruct: Some "evolved" prompts are nonsensical

Training on bad data teaches bad habits.

### Step 4: Recommended approach

```
500 clean MACRO traces > 50K random garbage
```

Priority order:
1. Run generate_training_data.py with Gemini (30-50 tasks)
2. Hand-craft reasoning examples from real development sessions
3. Use ONLY Magicoder-OSS-Instruct-75K as external data (best quality)
4. Quality-filter everything: discard failed runs and trivial examples

### Step 5: Training mix

```
50% — MACRO pipeline traces (your custom format)
30% — Filtered Magicoder examples (general coding ability)
20% — Hand-crafted reasoning from development logs
```

Quality over quantity. Always."""
            }
        ]
    },
]


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate seed training data from MACRO development sessions"
    )
    parser.add_argument(
        "--output", "-o",
        default="data/seed_train.jsonl",
        help="Output JSONL file",
    )
    
    args = parser.parse_args()
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for example in SEED_EXAMPLES:
            f.write(json.dumps(example) + "\n")
    
    # Count types
    print(f"  MACRO Seed Dataset Generated")
    print(f"  {'=' * 40}")
    print(f"  Total examples: {len(SEED_EXAMPLES)}")
    print(f"  Output: {output_path}")
    print()
    print(f"  Examples:")
    for i, ex in enumerate(SEED_EXAMPLES, 1):
        user_msg = ex["messages"][1]["content"][:60]
        print(f"    {i}. {user_msg}...")
    
    print(f"\n  Merge with: python format_dataset.py to combine all data sources")


if __name__ == "__main__":
    main()
