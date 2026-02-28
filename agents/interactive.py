"""
Interactive CLI mode for Contextual Architect.

Provides a chat-like terminal session where users can
send multiple requests to the pipeline without restarting.

Features:
  - Colored prompt with project info
  - @file reference parsing
  - Special commands: exit, help, status, config
  - Session history
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import Optional

from .orchestrator import Orchestrator, OrchestrationResult
from .config import AgentConfig
from .llm_client import create_llm_client, detect_provider_from_env
from .logger import get_logger


# ── ANSI Colors ───────────────────────────────────────────
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    BG_DARK = "\033[40m"
    
    @staticmethod
    def colored(text: str, color: str) -> str:
        return f"{color}{text}{Colors.RESET}"


def print_banner(repo_path: str, provider: str, lang: str, config: AgentConfig):
    """Print the startup banner."""
    print()
    print(Colors.colored("  ╔══════════════════════════════════════════════════╗", Colors.CYAN))
    print(Colors.colored("  ║", Colors.CYAN) + Colors.colored("  🏗️  CONTEXTUAL ARCHITECT", Colors.BOLD + Colors.WHITE) + Colors.colored("                        ║", Colors.CYAN))
    print(Colors.colored("  ║", Colors.CYAN) + Colors.colored("  AI-powered enterprise code generation", Colors.DIM + Colors.WHITE) + Colors.colored("           ║", Colors.CYAN))
    print(Colors.colored("  ╚══════════════════════════════════════════════════╝", Colors.CYAN))
    print()
    print(Colors.colored("  📁 Repo:     ", Colors.DIM) + Colors.colored(repo_path, Colors.WHITE))
    print(Colors.colored("  🔧 Language: ", Colors.DIM) + Colors.colored(lang, Colors.WHITE))
    print(Colors.colored("  🤖 Provider: ", Colors.DIM) + Colors.colored(provider, Colors.GREEN))
    
    if config.planner_provider:
        print(Colors.colored("  🧠 Planner:  ", Colors.DIM) + Colors.colored(config.planner_provider, Colors.YELLOW))
    if config.implementer_provider:
        print(Colors.colored("  ⚙️  Implmtr:  ", Colors.DIM) + Colors.colored(config.implementer_provider, Colors.YELLOW))
    
    print()
    print(Colors.colored("  Type your request, or use these commands:", Colors.DIM))
    print(Colors.colored("    help", Colors.CYAN) + Colors.colored("      — show all commands and features", Colors.DIM))
    print(Colors.colored("    exit", Colors.CYAN) + Colors.colored("      — quit the session", Colors.DIM))
    print(Colors.colored("    @file.py", Colors.CYAN) + Colors.colored("   — reference a file in your request", Colors.DIM))
    print()
    print(Colors.colored("  Supported: ", Colors.DIM) + Colors.colored("python │ cpp │ c │ go │ typescript │ javascript │ java", Colors.WHITE))
    print()


def print_help():
    """Print available commands."""
    print()
    print(Colors.colored("  Commands:", Colors.BOLD))
    print(Colors.colored("  ─────────────────────────────────────", Colors.DIM))
    print(Colors.colored("    help", Colors.CYAN) + "          Show this help message")
    print(Colors.colored("    exit / quit", Colors.CYAN) + "   End the session")
    print(Colors.colored("    status", Colors.CYAN) + "        Show current configuration")
    print(Colors.colored("    config", Colors.CYAN) + "        Show saved config path")
    print(Colors.colored("    clear", Colors.CYAN) + "         Clear the screen")
    print()
    print(Colors.colored("  How to Use:", Colors.BOLD))
    print(Colors.colored("  ─────────────────────────────────────", Colors.DIM))
    print("    Just type what you want to build in plain English:")
    print(Colors.colored("    ❯", Colors.GREEN) + " Add user authentication")
    print(Colors.colored("    ❯", Colors.GREEN) + " Create a linked list implementation")
    print(Colors.colored("    ❯", Colors.GREEN) + " Add binary search to @sorting.cpp")
    print()
    print(Colors.colored("  File References (@):", Colors.BOLD))
    print(Colors.colored("  ─────────────────────────────────────", Colors.DIM))
    print("    Use @ before a filename to modify an existing file:")
    print(Colors.colored("    ❯", Colors.GREEN) + " Add booking to @Movie_ticket_pricing.py")
    print(Colors.colored("    ❯", Colors.GREEN) + " Fix bug in @utils/auth.cpp")
    print("    Without @, a new file is created.")
    print()
    print(Colors.colored("  Supported Languages:", Colors.BOLD))
    print(Colors.colored("  ─────────────────────────────────────", Colors.DIM))
    print("    python │ cpp │ c │ go │ typescript │ javascript │ java")
    print("    Set with: --lang cpp")
    print()


def parse_file_references(request: str, repo_path: str) -> str:
    """Parse @file references in the request.
    
    Converts @filename to the relative path if the file exists.
    Example: "Add to @utils.py" stays as "Add to utils.py"
    """
    import re
    
    # Find @file references
    pattern = r"@([\w/\\.-]+)"
    matches = re.findall(pattern, request)
    
    for match in matches:
        full_path = Path(repo_path) / match
        if full_path.exists():
            # Replace @file with just the filename (the pipeline will detect it)
            request = request.replace(f"@{match}", match)
        else:
            # Try recursive search
            basename = Path(match).name
            for f in Path(repo_path).rglob(basename):
                if ".contextual-architect" not in str(f):
                    rel = str(f.relative_to(Path(repo_path))).replace("\\", "/")
                    request = request.replace(f"@{match}", rel)
                    break
    
    return request


async def run_single_request(
    request: str,
    repo_path: str,
    lang: str,
    config: AgentConfig,
    llm_client,
    verbose: bool = False,
) -> Optional[OrchestrationResult]:
    """Run a single request through the pipeline."""
    from .__main__ import print_result
    
    orchestrator = Orchestrator(llm_client=llm_client, config=config)
    
    try:
        result = await orchestrator.run(
            user_request=request,
            repo_path=repo_path,
            language=lang,
        )
        print_result(result, orchestrator)
        return result
    except KeyboardInterrupt:
        print("\n  ⚠️  Request interrupted.")
        return None
    except Exception as e:
        print(Colors.colored(f"\n  ❌ Error: {e}", Colors.RED))
        if verbose:
            import traceback
            traceback.print_exc()
        return None


async def interactive_session(args) -> int:
    """Run an interactive chat session."""
    
    # Resolve repo path
    repo_path = os.path.abspath(args.repo)
    if not os.path.isdir(repo_path):
        print(Colors.colored(f"  ❌ Repository path does not exist: {repo_path}", Colors.RED))
        return 1
    
    # Determine provider — Priority: CLI args > env vars > config file
    saved_config = AgentConfig.load_user_config()
    
    if args.provider:
        provider = args.provider
        api_key = args.api_key
    else:
        provider, api_key = detect_provider_from_env()
        if provider == "mock" and saved_config.llm_provider != "mock":
            provider = saved_config.llm_provider
            api_key = saved_config.llm_api_key
    
    api_key = args.api_key or api_key or saved_config.llm_api_key
    
    # Per-agent providers: CLI args > saved config
    planner_provider = getattr(args, 'planner_provider', None) or saved_config.planner_provider
    planner_api_key = saved_config.planner_api_key
    implementer_provider = getattr(args, 'implementer_provider', None) or saved_config.implementer_provider
    implementer_api_key = saved_config.implementer_api_key
    
    if provider == "mock":
        print(Colors.colored(
            "  ⚠️  No LLM provider detected. Set GROQ_API_KEY, GOOGLE_API_KEY, etc.",
            Colors.YELLOW,
        ))
        return 1
    
    # Build config
    config = AgentConfig(
        llm_provider=provider,
        llm_model=args.model,
        llm_api_key=api_key,
        max_retries=args.max_retries,
        use_external_tools=not args.no_external_tools,
        log_level="DEBUG" if args.verbose else "INFO",
        log_format="pretty",
        planner_provider=planner_provider,
        planner_api_key=planner_api_key,
        implementer_provider=implementer_provider,
        implementer_api_key=implementer_api_key,
    )
    
    # Create LLM client
    try:
        llm_client = create_llm_client(
            provider=config.llm_provider,
            model=config.llm_model,
            api_key=config.llm_api_key,
        )
    except ValueError as e:
        print(Colors.colored(f"  ❌ Failed to create LLM client: {e}", Colors.RED))
        return 1
    
    lang = args.lang
    verbose = args.verbose
    
    # Print banner
    print_banner(repo_path, provider, lang, config)
    
    # Track session
    request_count = 0
    
    # Interactive loop
    while True:
        try:
            # Prompt
            prompt = Colors.colored("  ❯ ", Colors.GREEN + Colors.BOLD)
            user_input = input(prompt).strip()
            
            if not user_input:
                continue
            
            # Handle commands
            cmd = user_input.lower()
            
            if cmd in ("exit", "quit", "q"):
                print(Colors.colored(f"\n  👋 Session ended. {request_count} requests processed.\n", Colors.DIM))
                return 0
            
            elif cmd == "help":
                print_help()
                continue
            
            elif cmd == "clear":
                os.system("cls" if os.name == "nt" else "clear")
                print_banner(repo_path, provider, lang, config)
                continue
            
            elif cmd == "status":
                print()
                print(Colors.colored("  Current Status:", Colors.BOLD))
                print(f"    Repo:       {repo_path}")
                print(f"    Language:   {lang}")
                print(f"    Provider:   {provider}")
                print(f"    Model:      {llm_client.model_name}")
                if config.planner_provider:
                    print(f"    Planner:    {config.planner_provider}")
                if config.implementer_provider:
                    print(f"    Implementer: {config.implementer_provider}")
                print(f"    Requests:   {request_count}")
                print()
                continue
            
            elif cmd == "config":
                config_path = AgentConfig.config_dir() / "config.json"
                if config_path.exists():
                    print(f"\n  📄 Config: {config_path}")
                else:
                    print(f"\n  ℹ️  No saved config. Use --save-config to create one.")
                print()
                continue
            
            # Parse @file references
            request = parse_file_references(user_input, repo_path)
            
            # Run the pipeline
            print()
            request_count += 1
            await run_single_request(
                request=request,
                repo_path=repo_path,
                lang=lang,
                config=config,
                llm_client=llm_client,
                verbose=verbose,
            )
            print()
        
        except KeyboardInterrupt:
            print(Colors.colored(f"\n\n  👋 Session ended. {request_count} requests processed.\n", Colors.DIM))
            return 0
        
        except EOFError:
            print(Colors.colored(f"\n\n  👋 Session ended. {request_count} requests processed.\n", Colors.DIM))
            return 0
