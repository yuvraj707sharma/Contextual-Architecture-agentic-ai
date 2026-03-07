"""
Setup Wizard -- Interactive first-time setup for MACRO.

Guides users through:
1. System checks (Python version, dependencies)
2. API key selection (with recommendations)
3. Connection testing
4. Config save + next steps
"""

import importlib
import os
import sys
from typing import Optional, Tuple

# ASCII-safe output only (no emoji -- Windows cmd compatibility)

PROVIDERS = [
    {
        "name": "Google Gemini",
        "id": "google",
        "env_var": "GOOGLE_API_KEY",
        "prefix": "AIza",
        "cost": "FREE (15 req/min)",
        "quality": "Excellent",
        "recommended": True,
        "signup": "https://aistudio.google.com/apikey",
    },
    {
        "name": "Groq",
        "id": "groq",
        "env_var": "GROQ_API_KEY",
        "prefix": "gsk_",
        "cost": "FREE (30 req/min)",
        "quality": "Fast, good for code",
        "recommended": True,
        "signup": "https://console.groq.com/keys",
    },
    {
        "name": "OpenAI",
        "id": "openai",
        "env_var": "OPENAI_API_KEY",
        "prefix": "sk-",
        "cost": "Paid ($2.50-$5/M tokens)",
        "quality": "Excellent",
        "recommended": False,
        "signup": "https://platform.openai.com/api-keys",
    },
    {
        "name": "Anthropic (Claude)",
        "id": "anthropic",
        "env_var": "ANTHROPIC_API_KEY",
        "prefix": "sk-ant-",
        "cost": "Paid ($3-$15/M tokens)",
        "quality": "Best reasoning",
        "recommended": False,
        "signup": "https://console.anthropic.com/",
    },
    {
        "name": "DeepSeek",
        "id": "deepseek",
        "env_var": "DEEPSEEK_API_KEY",
        "prefix": "sk-",
        "cost": "Cheap ($0.14/M tokens)",
        "quality": "Good for code",
        "recommended": False,
        "signup": "https://platform.deepseek.com/",
    },
]


def _clear_screen():
    """Clear terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def _print_header():
    """Print the MACRO setup banner."""
    print()
    print("  +" + "-" * 50 + "+")
    print("  |                                                  |")
    print("  |          MACRO -- First-Time Setup                |")
    print("  |  Multi-Agent Contextual Repository Orchestrator   |")
    print("  |                                                  |")
    print("  +" + "-" * 50 + "+")
    print()


def _print_step(step: int, total: int, title: str):
    """Print a step header."""
    print(f"  [{step}/{total}] {title}")
    print("  " + "-" * 45)


def _input_choice(prompt: str, valid: list, default: str = "") -> str:
    """Get user input with validation."""
    while True:
        suffix = f" [{default}]" if default else ""
        try:
            choice = input(f"  {prompt}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  Setup cancelled.")
            sys.exit(0)

        if not choice and default:
            return default
        if choice in valid:
            return choice
        print(f"  Invalid choice. Options: {', '.join(valid)}")


def _input_text(prompt: str, hidden: bool = False) -> str:
    """Get text input from user."""
    while True:
        try:
            if hidden:
                import getpass
                value = getpass.getpass(f"  {prompt}: ")
            else:
                value = input(f"  {prompt}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  Setup cancelled.")
            sys.exit(0)

        if value:
            return value
        print("  Please enter a value.")


def check_python() -> bool:
    """Check Python version."""
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 10
    status = "OK" if ok else "FAIL (need 3.10+)"
    print(f"    Python {v.major}.{v.minor}.{v.micro} ... {status}")
    return ok


def check_dependencies() -> Tuple[bool, list]:
    """Check required dependencies."""
    required = [
        ("httpx", "httpx"),
        ("google.genai", "google-genai"),
    ]
    optional = [
        ("chromadb", "chromadb"),
    ]

    missing = []
    for module, pip_name in required:
        try:
            importlib.import_module(module)
            print(f"    {pip_name} ... OK")
        except ImportError:
            print(f"    {pip_name} ... MISSING")
            missing.append(pip_name)

    for module, pip_name in optional:
        try:
            importlib.import_module(module)
            print(f"    {pip_name} ... OK (optional)")
        except ImportError:
            print(f"    {pip_name} ... not installed (optional, for RAG)")

    return len(missing) == 0, missing


def detect_existing_keys() -> list:
    """Detect API keys already set in environment."""
    found = []
    for p in PROVIDERS:
        key = os.environ.get(p["env_var"])
        if key:
            masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
            found.append((p, masked))
    return found


def test_api_key(provider_id: str, api_key: str) -> Tuple[bool, str]:
    """Test if an API key works by making a minimal API call."""
    try:
        from .llm_client import create_llm_client
        client = create_llm_client(
            provider=provider_id,
            api_key=api_key,
        )
        # Make a tiny test call
        response = client.generate(
            system_prompt="Reply with exactly: OK",
            user_prompt="Test connection. Reply with exactly one word: OK",
            temperature=0.0,
            max_tokens=10,
        )
        if response and response.content:
            return True, client.model_name
        return False, "Empty response"
    except Exception as e:
        error_msg = str(e)
        # Common error patterns
        if "401" in error_msg or "403" in error_msg or "invalid" in error_msg.lower():
            return False, "Invalid API key"
        if "429" in error_msg or "rate" in error_msg.lower():
            return True, "Rate limited (key is valid)"  # Key works, just throttled
        return False, error_msg[:100]


def select_provider_interactive() -> Tuple[str, str]:
    """Interactive provider selection with recommendations."""
    print()
    print("  Available providers:")
    print()

    for i, p in enumerate(PROVIDERS, 1):
        tag = " <-- Recommended (FREE)" if p["recommended"] else ""
        print(f"    [{i}] {p['name']:<22} {p['cost']}{tag}")

    print(f"    [{len(PROVIDERS) + 1}] I already have a key set in environment variables")
    print()

    valid = [str(i) for i in range(1, len(PROVIDERS) + 2)]
    choice = _input_choice("Enter choice", valid, "1")
    idx = int(choice) - 1

    # Check for "already have env var" option
    if idx == len(PROVIDERS):
        existing = detect_existing_keys()
        if existing:
            p, masked = existing[0]
            print(f"\n    Found: {p['env_var']} = {masked}")
            return p["id"], os.environ.get(p["env_var"])
        else:
            print("\n    No API keys found in environment variables.")
            print("    Set one with: set GOOGLE_API_KEY=your_key_here")
            print("    Then run: macro --setup")
            sys.exit(1)

    provider = PROVIDERS[idx]

    print(f"\n  Selected: {provider['name']}")
    print(f"  Get your key at: {provider['signup']}")
    print()

    api_key = _input_text(f"Paste your {provider['name']} API key")
    return provider["id"], api_key


def ask_multi_provider() -> Tuple[Optional[str], Optional[str]]:
    """Ask user if they want a secondary provider for smart agents."""
    print()
    print("  MACRO can use 2 providers for better results:")
    print("    - Fast provider   -> Historian, Reviewer (speed)")
    print("    - Smart provider  -> Planner, Implementer (quality)")
    print()
    print("  Example: Groq (fast) + Gemini (smart)")
    print()

    choice = _input_choice(
        "Add a second provider for planning? (y/n)",
        ["y", "n", "Y", "N", "yes", "no"],
        "n",
    )

    if choice.lower() in ("y", "yes"):
        print()
        print("  Select the SMART provider (for Planner + Implementer):")
        for i, p in enumerate(PROVIDERS, 1):
            print(f"    [{i}] {p['name']:<22} {p['cost']}")

        valid = [str(i) for i in range(1, len(PROVIDERS) + 1)]
        idx = int(_input_choice("Enter choice", valid)) - 1
        provider = PROVIDERS[idx]

        print(f"\n  Selected: {provider['name']} for planning")
        api_key = _input_text(f"Paste your {provider['name']} API key")
        return provider["id"], api_key

    return None, None


def run_setup():
    """Main setup wizard entry point."""
    _clear_screen()
    _print_header()

    total_steps = 4

    # ── Step 1: System Check ──────────────────────────────
    _print_step(1, total_steps, "System Check")
    print()

    py_ok = check_python()
    if not py_ok:
        print("\n  [X] Python 3.10+ is required. Please upgrade.")
        sys.exit(1)

    deps_ok, missing = check_dependencies()
    if not deps_ok:
        print(f"\n  [!] Missing dependencies: {', '.join(missing)}")
        print("  Run: pip install -r requirements.txt")
        print("  Then run: macro --setup")
        sys.exit(1)

    print("\n  [OK] System check passed.\n")

    # ── Step 2: API Key Selection ─────────────────────────
    _print_step(2, total_steps, "API Key Configuration")

    # Check for existing keys first
    existing = detect_existing_keys()
    if existing:
        print("\n  Found existing API keys:")
        for p, masked in existing:
            print(f"    - {p['env_var']} = {masked}")
        print()
        use_existing = _input_choice(
            "Use existing key(s)? (y/n)",
            ["y", "n", "Y", "N", "yes", "no"],
            "y",
        )
        if use_existing.lower() in ("y", "yes"):
            provider_id = existing[0][0]["id"]
            api_key = os.environ.get(existing[0][0]["env_var"])
        else:
            provider_id, api_key = select_provider_interactive()
    else:
        provider_id, api_key = select_provider_interactive()

    # ── Step 3: Test Connection ───────────────────────────
    _print_step(3, total_steps, "Testing Connection")
    print()
    print(f"  Testing {provider_id} API key...", end=" ", flush=True)

    ok, model_or_error = test_api_key(provider_id, api_key)

    if ok:
        print(f"OK ({model_or_error})")
    else:
        print("FAILED")
        print(f"\n  Error: {model_or_error}")
        print("\n  Please check your API key and try again.")
        retry = _input_choice(
            "Save anyway and fix later? (y/n)",
            ["y", "n", "Y", "N"],
            "n",
        )
        if retry.lower() == "n":
            sys.exit(1)

    # Ask about multi-provider
    planner_provider, planner_api_key = ask_multi_provider()

    # ── Step 4: Save Config ───────────────────────────────
    print()
    _print_step(4, total_steps, "Saving Configuration")
    print()

    from .config import AgentConfig

    # When user picks a smart provider, route BOTH planner AND implementer to it
    config = AgentConfig(
        llm_provider=provider_id,
        llm_api_key=api_key,
        planner_provider=planner_provider,
        planner_api_key=planner_api_key,
        implementer_provider=planner_provider,  # Same smart provider for implementer
        implementer_api_key=planner_api_key,
    )

    path = config.save_to_file()
    print(f"  Config saved to: {path}")

    # ── Done ──────────────────────────────────────────────
    print()
    print("  +" + "-" * 50 + "+")
    print("  |                                                  |")
    print("  |          Setup Complete!                          |")
    print("  |                                                  |")
    print("  +" + "-" * 50 + "+")
    print()
    print("  Try these commands:")
    print()
    print('    macro -i --repo "C:\\path\\to\\project" --lang python')
    print("      Start interactive mode on a project")
    print()
    print('    macro "Add login endpoint" --repo . --lang python')
    print("      One-shot code generation")
    print()
    print("    macro --help")
    print("      See all options")
    print()

    if planner_provider:
        print("  Your config:")
        print(f"    Main provider:    {provider_id} (fast agents)")
        print(f"    Planner provider: {planner_provider} (smart agents)")
    else:
        print(f"  Provider: {provider_id} (all agents)")

    print()
