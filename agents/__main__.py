"""
CLI entry point for Contextual Architect.

Usage:
    python -m agents "Add JWT authentication middleware" --repo ./myproject --lang python
    python -m agents -i --repo ./myproject --lang python  # interactive mode
    python -m agents --help
"""

import argparse
import asyncio
import sys
import os

from .orchestrator import Orchestrator, OrchestrationResult
from .config import AgentConfig
from .llm_client import create_llm_client
from .logger import get_logger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contextual-architect",
        description=(
            "Contextual Architect — AI that writes production-grade, "
            "enterprise-ready code by learning from project evolution."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single-shot mode
  python -m agents "Add JWT auth middleware" --repo ./myproject --lang python

  # Multi-provider (Gemini for planning, Groq for fast agents)
  python -m agents "Add caching" --repo ./myproject --provider groq --planner-provider google

  # Interactive chat mode
  python -m agents -i --repo ./myproject --lang python

  # Save config for reuse
  python -m agents --save-config --provider groq --planner-provider google
        """,
    )

    # Positional argument: the user request (optional for interactive mode)
    parser.add_argument(
        "request",
        type=str,
        nargs="?",
        default=None,
        help='What you want to build (e.g., "Add JWT authentication middleware")',
    )

    # Required arguments
    parser.add_argument(
        "--repo", "-r",
        type=str,
        default=".",
        help="Path to the repository (default: current directory)",
    )
    parser.add_argument(
        "--lang", "-l",
        type=str,
        default="python",
        choices=["python", "go", "typescript", "javascript", "cpp", "c", "java"],
        help="Programming language (default: python)",
    )

    # LLM configuration
    parser.add_argument(
        "--provider", "-p",
        type=str,
        default=None,
        choices=["groq", "deepseek", "openai", "anthropic", "google", "ollama", "mock"],
        help="Default LLM provider (default: auto-detect from env vars)",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=None,
        help="Specific model override (e.g., gpt-4o, claude-3-5-sonnet-20241022)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key (alternative to environment variable)",
    )

    # Per-agent provider routing
    parser.add_argument(
        "--planner-provider",
        type=str,
        default=None,
        choices=["groq", "deepseek", "openai", "anthropic", "google", "ollama"],
        help="LLM provider for Planner + Alignment agents (e.g., google for Gemini)",
    )
    parser.add_argument(
        "--implementer-provider",
        type=str,
        default=None,
        choices=["groq", "deepseek", "openai", "anthropic", "google", "ollama"],
        help="LLM provider for Implementer + Test Generator agents",
    )

    # Pipeline configuration
    parser.add_argument(
        "--pseudocode", "--pseudo",
        type=str,
        default=None,
        help=(
            'User-provided pseudocode to anchor code generation. '
            'Can be inline text or a path to a .txt/.md file. '
            'Example: --pseudocode "1. Check auth header\\n2. Decode JWT\\n3. Attach user"'
        ),
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max retry attempts if Reviewer rejects code (default: 3)",
    )
    parser.add_argument(
        "--no-external-tools",
        action="store_true",
        help="Disable external linters (ruff, mypy, golangci-lint)",
    )

    # Interactive mode
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Start interactive chat session",
    )
    parser.add_argument(
        "--save-config",
        action="store_true",
        help="Save current CLI settings to ~/.contextual-architect/config.json",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive first-time setup wizard",
    )

    # Output configuration
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of pretty-printed",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated without writing files",
    )

    return parser


def auto_detect_provider() -> str:
    """Auto-detect LLM provider from available environment variables."""
    from .llm_client import detect_provider_from_env
    provider, _ = detect_provider_from_env()
    return provider


def print_result(result: OrchestrationResult, orchestrator: Orchestrator, as_json: bool = False):
    """Pretty-print the orchestration result."""
    if as_json:
        import json
        output = {
            "success": result.success,
            "target_file": result.target_file,
            "attempts": result.attempts,
            "errors": result.errors,
            "agent_summaries": result.agent_summaries,
            "generated_code": result.generated_code,
            "validation": result.validation.to_dict() if result.validation else None,
            "metrics": result.metrics.summary() if result.metrics else None,
        }
        print(json.dumps(output, indent=2))
        return

    print()
    print("=" * 70)
    print("  MACRO — RESULT")
    print("=" * 70)
    print()

    if result.success:
        print("  ✅ SUCCESS")
    else:
        print("  ❌ FAILED")
        for err in result.errors:
            print(f"     Error: {err}")
        print()
        return

    print(f"  > Target File:  {result.target_file}")
    print(f"  > Attempts:     {result.attempts}")
    print()

    # Agent summaries
    print("  > Agent Summaries:")
    for agent_name, summary in result.agent_summaries.items():
        print(f"     [{agent_name}] {summary}")
    print()

    # Validation
    if result.validation:
        print(f"  > Validation:   {result.validation.summary}")
        if result.validation.warnings:
            for w in result.validation.warnings[:5]:
                print(f"     [!] {w.message}")
    print()

    # Metrics
    if result.metrics:
        print(f"  > Duration:     {result.metrics.total_duration_ms:.0f}ms")
        if result.metrics.retries > 0:
            print(f"  > Retries:      {result.metrics.retries}")
    print()

    # Show proposed changes
    if result.changeset:
        changes_output = orchestrator.show_changes(result)
        print("  > Proposed Changes:")
        for line in changes_output.split("\n"):
            print(f"     {line}")
        print()

    # Show generated code preview
    if result.generated_code:
        print("  > Generated Code Preview:")
        print("  " + "-" * 60)
        lines = result.generated_code.split("\n")
        for line in lines[:40]:
            print(f"  | {line}")
        if len(lines) > 40:
            print(f"  | ... ({len(lines) - 40} more lines)")
        print("  " + "-" * 60)
    print()


async def run(args) -> int:
    """Run the orchestration pipeline."""
    logger = get_logger(
        "cli",
        level="DEBUG" if args.verbose else "INFO",
        fmt="pretty",
    )

    # Resolve repo path
    repo_path = os.path.abspath(args.repo)
    if not os.path.isdir(repo_path):
        logger.error(f"Repository path does not exist: {repo_path}")
        return 1

    # Determine provider and API key
    # Priority: CLI args > env vars > config file
    from .llm_client import detect_provider_from_env
    
    # Load saved config as fallback
    saved_config = AgentConfig.load_user_config()
    
    if args.provider:
        provider = args.provider
        detected_key = args.api_key
    else:
        # Try env vars first
        provider, detected_key = detect_provider_from_env()
        # If nothing in env, use saved config
        if provider == "mock" and saved_config.llm_provider != "mock":
            provider = saved_config.llm_provider
            detected_key = saved_config.llm_api_key
    
    # CLI --api-key flag overrides everything
    api_key = args.api_key or detected_key or saved_config.llm_api_key
    
    # Per-agent providers: CLI args > saved config
    planner_provider = getattr(args, 'planner_provider', None) or saved_config.planner_provider
    planner_api_key = saved_config.planner_api_key
    implementer_provider = getattr(args, 'implementer_provider', None) or saved_config.implementer_provider
    implementer_api_key = saved_config.implementer_api_key

    if provider == "mock":
        logger.warning(
            "No LLM provider detected. Using mock (placeholder code). "
            "Set DEEPSEEK_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY, or ANTHROPIC_API_KEY "
            "to enable real code generation."
        )

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
        if provider == "mock":
            llm_client = None
        else:
            logger.error(f"Failed to create LLM client: {e}")
            return 1

    # Load pseudocode (from flag — can be inline text or file path)
    user_pseudocode = None
    if args.pseudocode:
        pseudo_path = os.path.abspath(args.pseudocode)
        if os.path.isfile(pseudo_path):
            with open(pseudo_path, "r", encoding="utf-8") as f:
                user_pseudocode = f.read().strip()
            logger.info(f"Loaded pseudocode from: {pseudo_path}")
        else:
            user_pseudocode = args.pseudocode.strip()

    # Print banner
    print()
    print("MACRO -- Multi-Agent Contextual Repository Orchestrator")
    print(f"   Request:  {args.request}")
    print(f"   Repo:     {repo_path}")
    print(f"   Language: {args.lang}")
    print(f"   Provider: {provider}" + (f" ({args.model})" if args.model else ""))
    print(f"   Retries:  {args.max_retries}")
    if user_pseudocode:
        print(f"   Pseudo:   {user_pseudocode[:80]}..." if len(user_pseudocode) > 80 else f"   Pseudo:   {user_pseudocode}")
    print()

    # Run pipeline
    orchestrator = Orchestrator(llm_client=llm_client, config=config)

    try:
        result = await orchestrator.run(
            user_request=args.request,
            repo_path=repo_path,
            language=args.lang,
            user_pseudocode=user_pseudocode,
        )
    except KeyboardInterrupt:
        print("\n\n  Interrupted by user.")
        return 1
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    # Print result
    print_result(result, orchestrator, as_json=args.json)

    # If dry run, stop here
    if args.dry_run:
        print("  Dry run -- no files written.")
        return 0 if result.success else 1

    # If there's a changeset with permissions needed, handle it
    if result.changeset and result.changeset.needs_permission:
        print("  [!] Some changes require your approval.")
        print("     Run with --dry-run to preview without writing.")
        # In future: interactive approval loop here

    return 0 if result.success else 1


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Handle --setup wizard
    if args.setup:
        from .setup_wizard import run_setup
        run_setup()
        sys.exit(0)

    # Handle --save-config
    if args.save_config:
        from .llm_client import detect_provider_from_env
        provider = args.provider
        if not provider:
            provider, _ = detect_provider_from_env()
        config = AgentConfig(
            llm_provider=provider or "mock",
            llm_model=args.model,
            llm_api_key=args.api_key,
            planner_provider=getattr(args, 'planner_provider', None),
            implementer_provider=getattr(args, 'implementer_provider', None),
            default_language=args.lang,
        )
        path = config.save_to_file()
        print(f"\u2705 Config saved to: {path}")
        sys.exit(0)

    # Handle --interactive mode
    if args.interactive:
        from .interactive import interactive_session
        exit_code = asyncio.run(interactive_session(args))
        sys.exit(exit_code)

    # Single-shot mode requires a request
    if not args.request:
        parser.print_help()
        sys.exit(1)

    exit_code = asyncio.run(run(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
