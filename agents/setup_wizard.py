"""
Setup Wizard -- Interactive first-time setup for MACRO.

Guides users through:
1. System checks (Python version, dependencies)
2. API key selection (with recommendations)
3. Connection testing
4. Config save + next steps
"""

import asyncio
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
    {
        "name": "Ollama (Local)",
        "id": "ollama",
        "env_var": None,
        "prefix": "",
        "cost": "FREE (Local)",
        "quality": "Runs locally on your machine",
        "recommended": False,
        "signup": "https://ollama.com",
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


def test_api_key(provider_id: str, api_key: Optional[str], model: Optional[str] = None) -> Tuple[bool, str]:
    """Test if a provider works by making a minimal API call or checking service."""
    if provider_id == "ollama":
        import httpx
        try:
            resp = httpx.get("http://localhost:11434/api/version", timeout=3)
            if resp.status_code == 200:
                version = resp.json().get("version", "unknown")
                return True, f"Ollama is running (v{version})"
            return False, f"Ollama returned status {resp.status_code}"
        except Exception as e:
            return False, f"Could not connect to Ollama (make sure Ollama is running): {e}"

    try:
        from .llm_client import create_llm_client
        client = create_llm_client(
            provider=provider_id,
            api_key=api_key,
            model=model,
        )
        # Make a tiny test call (generate is async, so we run it synchronously)
        response = asyncio.run(client.generate(
            system_prompt="Reply with exactly: OK",
            user_prompt="Test connection. Reply with exactly one word: OK",
            temperature=0.0,
            max_tokens=10,
        ))
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


def get_or_prompt_key(provider_id: str, env_var: str, signup_url: str) -> Optional[str]:
    """Helper to detect key from environment or prompt user."""
    if provider_id == "ollama":
        return None

    # Check environment variable
    env_val = os.environ.get(env_var)
    if env_val:
        masked = env_val[:4] + "****" + env_val[-4:] if len(env_val) > 8 else "****"
        use_existing = _input_choice(
            f"Found existing {env_var} ({masked}). Use it? (y/n)",
            ["y", "n", "Y", "N", "yes", "no"],
            "y"
        )
        if use_existing.lower() in ("y", "yes"):
            return env_val

    # Prompt user
    print(f"  Get your API key at: {signup_url}")
    return _input_text("Paste your API key")


def get_preset_config(choice: str, api_key: Optional[str] = None, second_key: Optional[str] = None) -> dict:
    """Get AgentConfig parameters for a specific preset choice."""
    if choice == "1":
        return {
            "llm_provider": "google",
            "llm_model": "gemini-2.5-flash",
            "llm_api_key": api_key,
            "planner_provider": "google",
            "planner_model": "gemini-2.5-pro",
            "planner_api_key": api_key,
            "implementer_provider": "google",
            "implementer_model": "gemini-2.5-pro",
            "implementer_api_key": api_key,
        }
    elif choice == "2":
        return {
            "llm_provider": "anthropic",
            "llm_model": "claude-3-5-haiku-20241022",
            "llm_api_key": api_key,
            "planner_provider": "anthropic",
            "planner_model": "claude-4.5-sonnet",
            "planner_api_key": api_key,
            "implementer_provider": "anthropic",
            "implementer_model": "claude-4.5-sonnet",
            "implementer_api_key": api_key,
        }
    elif choice == "3":
        return {
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
            "llm_api_key": api_key,
            "planner_provider": "openai",
            "planner_model": "gpt-4o",
            "planner_api_key": api_key,
            "implementer_provider": "openai",
            "implementer_model": "gpt-4o",
            "implementer_api_key": api_key,
        }
    elif choice == "4":
        return {
            "llm_provider": "groq",
            "llm_model": "llama-3.3-70b-versatile",
            "llm_api_key": api_key,
            "planner_provider": "google",
            "planner_model": "gemini-2.5-pro",
            "planner_api_key": second_key,
            "implementer_provider": "google",
            "implementer_model": "gemini-2.5-pro",
            "implementer_api_key": second_key,
        }
    return {}


def run_custom_setup_flow(total_steps: int) -> dict:
    """Run a custom setup flow where each agent is manually configured."""
    print("  [Custom Setup Mode]")
    print("  We will configure the Main (Utility) provider first, followed by custom agent overrides.")
    print()

    # 1. Main Provider
    print("  Step 2a: Select Main (Utility) Provider")
    print("  (Used for fast background operations like Historian, Reviewer, scanner)")
    print()
    for i, p in enumerate(PROVIDERS, 1):
        print(f"    [{i}] {p['name']:<22} {p['cost']}")
    print()

    valid_providers = [str(i) for i in range(1, len(PROVIDERS) + 1)]
    choice = int(_input_choice("Enter choice", valid_providers, "1")) - 1
    main_p = PROVIDERS[choice]

    main_key = None
    if main_p["env_var"]:
        main_key = get_or_prompt_key(main_p["id"], main_p["env_var"], main_p["signup"])

    # Model override for main provider
    main_model = None
    custom_model = _input_choice(
        f"Use a custom model for {main_p['name']} instead of the default? (y/n)",
        ["y", "n", "Y", "N"],
        "n"
    )
    if custom_model.lower() == "y":
        main_model = _input_text("Enter model name")

    # Test main connection
    print()
    print(f"  Testing main connection ({main_p['id']} / {main_model or 'default'})...", end=" ", flush=True)
    ok, msg = test_api_key(main_p["id"], main_key, main_model)
    if ok:
        print(f"OK ({msg})")
    else:
        print("FAILED")
        print(f"  Error: {msg}")
        if _input_choice("Keep anyway? (y/n)", ["y", "n", "Y", "N"], "y").lower() == "n":
            sys.exit(1)

    params = {
        "llm_provider": main_p["id"],
        "llm_model": main_model,
        "llm_api_key": main_key,
    }

    # Helper to configure agent override
    def configure_agent_override(agent_name: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        print()
        override = _input_choice(
            f"Configure custom provider/model override for {agent_name}? (y/n)",
            ["y", "n", "Y", "N"],
            "n"
        )
        if override.lower() not in ("y", "yes"):
            return None, None, None

        print(f"\n  Select provider for {agent_name}:")
        for idx, pr in enumerate(PROVIDERS, 1):
            print(f"    [{idx}] {pr['name']:<22}")
        print()

        valid_idx = [str(idx) for idx in range(1, len(PROVIDERS) + 1)]
        choice_idx = int(_input_choice("Enter choice", valid_idx)) - 1
        agent_p = PROVIDERS[choice_idx]

        agent_key = None
        if agent_p["env_var"]:
            agent_key = get_or_prompt_key(agent_p["id"], agent_p["env_var"], agent_p["signup"])

        # Prompt for model override
        agent_model = _input_text("Enter model name (or hit Enter for provider default)")
        if not agent_model:
            agent_model = None

        # Test key
        print()
        print(f"  Testing connection for {agent_name}...", end=" ", flush=True)
        ok_a, msg_a = test_api_key(agent_p["id"], agent_key, agent_model)
        if ok_a:
            print(f"OK ({msg_a})")
        else:
            print("FAILED")
            print(f"  Error: {msg_a}")
            if _input_choice("Keep anyway? (y/n)", ["y", "n", "Y", "N"], "y").lower() == "n":
                sys.exit(1)

        return agent_p["id"], agent_model, agent_key

    # 2. Planner Override
    pl_provider, pl_model, pl_key = configure_agent_override("Planner")
    if pl_provider:
        params["planner_provider"] = pl_provider
        params["planner_model"] = pl_model
        params["planner_api_key"] = pl_key

    # 3. Implementer Override
    imp_provider, imp_model, imp_key = configure_agent_override("Implementer (Coder)")
    if imp_provider:
        params["implementer_provider"] = imp_provider
        params["implementer_model"] = imp_model
        params["implementer_api_key"] = imp_key

    return params


def run_setup():
    """Main setup wizard entry point with suggested configurations."""
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

    # ── Step 2: Choose Preset or Custom Setup ────────────────
    _print_step(2, total_steps, "Select Configuration Setup")
    print()
    print("  Choose one of our recommended setup configurations, or customize:")
    print()
    print("    [1] (Recommended) Google Gemini Hybrid (Single Provider)")
    print("        - Planner / Coder: gemini-2.5-pro (high reasoning)")
    print("        - Fast / Utility:  gemini-2.5-flash (fast & cost-effective)")
    print("        - Cost: Free tier available (15 RPM)")
    print()
    print("    [2] Anthropic Claude Hybrid (Single Provider)")
    print("        - Planner / Coder: claude-4.5-sonnet (best reasoning)")
    print("        - Fast / Utility:  claude-3-5-haiku-20241022 (fast utility)")
    print("        - Cost: Paid (~$3/M input tokens)")
    print()
    print("    [3] OpenAI Hybrid (Single Provider)")
    print("        - Planner / Coder: gpt-4o (excellent coding)")
    print("        - Fast / Utility:  gpt-4o-mini (cheap scan & helper)")
    print("        - Cost: Paid (~$2.50/M input tokens)")
    print()
    print("    [4] Multi-Provider Setup (Groq + Gemini)")
    print("        - Planner / Coder: gemini-2.5-pro (Google Gemini)")
    print("        - Fast / Utility:  llama-3.3-70b-versatile (Groq inference)")
    print("        - Cost: Gemini Pro key + Groq key (has free tier)")
    print()
    print("    [5] Custom / Advanced Setup (Manual Configuration)")
    print("        - Configure default, planner, implementer models & providers.")
    print()

    valid_choices = ["1", "2", "3", "4", "5"]
    choice = _input_choice("Select option", valid_choices, "1")
    print()

    config_params = {}

    if choice == "1":
        # Google Gemini Hybrid
        print("  [Google Gemini Hybrid Setup]")
        api_key = get_or_prompt_key("google", "GOOGLE_API_KEY", "https://aistudio.google.com/apikey")

        # Test connection
        _print_step(3, total_steps, "Testing Connection")
        print("  Testing Google Gemini API key (using gemini-2.5-flash)...", end=" ", flush=True)
        ok, msg = test_api_key("google", api_key, "gemini-2.5-flash")
        if ok:
            print(f"OK ({msg})")
        else:
            print("FAILED")
            print(f"  Error: {msg}")
            if _input_choice("Save anyway and fix later? (y/n)", ["y", "n", "Y", "N"], "n").lower() == "n":
                sys.exit(1)

        config_params = get_preset_config("1", api_key)

    elif choice == "2":
        # Anthropic Claude Hybrid
        print("  [Anthropic Claude Hybrid Setup]")
        api_key = get_or_prompt_key("anthropic", "ANTHROPIC_API_KEY", "https://console.anthropic.com/")

        # Test connection
        _print_step(3, total_steps, "Testing Connection")
        print("  Testing Anthropic API key (using claude-3-5-haiku-20241022)...", end=" ", flush=True)
        ok, msg = test_api_key("anthropic", api_key, "claude-3-5-haiku-20241022")
        if ok:
            print(f"OK ({msg})")
        else:
            print("FAILED")
            print(f"  Error: {msg}")
            if _input_choice("Save anyway and fix later? (y/n)", ["y", "n", "Y", "N"], "n").lower() == "n":
                sys.exit(1)

        config_params = get_preset_config("2", api_key)

    elif choice == "3":
        # OpenAI Hybrid
        print("  [OpenAI Hybrid Setup]")
        api_key = get_or_prompt_key("openai", "OPENAI_API_KEY", "https://platform.openai.com/api-keys")

        # Test connection
        _print_step(3, total_steps, "Testing Connection")
        print("  Testing OpenAI API key (using gpt-4o-mini)...", end=" ", flush=True)
        ok, msg = test_api_key("openai", api_key, "gpt-4o-mini")
        if ok:
            print(f"OK ({msg})")
        else:
            print("FAILED")
            print(f"  Error: {msg}")
            if _input_choice("Save anyway and fix later? (y/n)", ["y", "n", "Y", "N"], "n").lower() == "n":
                sys.exit(1)

        config_params = get_preset_config("3", api_key)

    elif choice == "4":
        # Multi-Provider Groq + Gemini
        print("  [Multi-Provider Setup (Groq + Gemini)]")
        groq_key = get_or_prompt_key("groq", "GROQ_API_KEY", "https://console.groq.com/keys")
        gemini_key = get_or_prompt_key("google", "GOOGLE_API_KEY", "https://aistudio.google.com/apikey")

        # Test connections
        _print_step(3, total_steps, "Testing Connections")

        print("  Testing Groq API key (using llama-3.3-70b-versatile)...", end=" ", flush=True)
        ok1, msg1 = test_api_key("groq", groq_key, "llama-3.3-70b-versatile")
        if ok1:
            print(f"OK ({msg1})")
        else:
            print("FAILED")
            print(f"  Error: {msg1}")

        print("  Testing Google Gemini API key (using gemini-2.5-pro)...", end=" ", flush=True)
        ok2, msg2 = test_api_key("google", gemini_key, "gemini-2.5-pro")
        if ok2:
            print(f"OK ({msg2})")
        else:
            print("FAILED")
            print(f"  Error: {msg2}")

        if not (ok1 and ok2):
            if _input_choice("Save anyway and fix later? (y/n)", ["y", "n", "Y", "N"], "n").lower() == "n":
                sys.exit(1)

        config_params = get_preset_config("4", groq_key, gemini_key)

    elif choice == "5":
        # Custom setup flow
        config_params = run_custom_setup_flow(total_steps)

    # ── Step 4: Save Config ───────────────────────────────
    print()
    _print_step(4, total_steps, "Saving Configuration")
    print()

    from .config import AgentConfig

    config = AgentConfig(**config_params)
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

    print("  Your config:")
    print(f"    Utility Provider:  {config.llm_provider} (model: {config.llm_model or 'default'})")
    if config.planner_provider:
        print(f"    Planner Provider:  {config.planner_provider} (model: {config.planner_model or 'default'})")
    if config.implementer_provider:
        print(f"    Coder Provider:    {config.implementer_provider} (model: {config.implementer_model or 'default'})")
    print()
