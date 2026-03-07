"""
CLI entry point for Contextual Architect.

Usage:
    python -m agents "Add JWT authentication middleware" --repo ./myproject --lang python
    python -m agents -i --repo ./myproject --lang python  # interactive mode
    python -m agents --help
"""

import argparse
import asyncio
import os
import sys

from .config import AgentConfig
from .llm_client import create_llm_client
from .logger import get_logger
from .orchestrator import OrchestrationResult, Orchestrator
from .safe_writer import SafeCodeWriter
from .shell_executor import ShellExecutor


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
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Auto-approve all file changes (skip permission prompts)",
    )

    return parser


def auto_detect_provider() -> str:
    """Auto-detect LLM provider from available environment variables."""
    from .llm_client import detect_provider_from_env
    provider, _ = detect_provider_from_env()
    return provider


def print_result(result: OrchestrationResult, orchestrator: Orchestrator, as_json: bool = False):
    """Pretty-print the orchestration result — clean, minimal, like Claude CLI."""
    DIM = "\033[2m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    if as_json:
        import json
        pipeline_dict = result.context.get("pipeline_report_dict")
        if pipeline_dict:
            output = pipeline_dict
        else:
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

    # ── Header: success/fail + timing ──
    duration = ""
    if result.metrics:
        duration = f" {DIM}({result.metrics.total_duration_ms/1000:.1f}s){RESET}"

    if result.success:
        print(f"  {GREEN}✓ Done{RESET}{duration}")
    else:
        print(f"  {RED}✗ Failed{RESET}{duration}")
        for err in result.errors:
            print(f"  {RED}  {err}{RESET}")
        print()
        return

    # ── Target file ──
    if result.target_file:
        print(f"  {DIM}target{RESET}  {result.target_file}")

    # ── Agent summaries — compact, dim ──
    if result.agent_summaries:
        for agent_name, summary in result.agent_summaries.items():
            if agent_name == "conflicts":
                continue
            # Truncate long summaries
            short = summary[:100] + "..." if len(summary) > 100 else summary
            print(f"  {DIM}{agent_name:12s}{short}{RESET}")

    # ── Validation ──
    if result.validation:
        v = result.validation
        if v.passed:
            print(f"  {GREEN}✓ review{RESET}  {DIM}{v.summary}{RESET}")
        else:
            print(f"  {YELLOW}! review{RESET}  {v.summary}")
            for w in (v.warnings or [])[:3]:
                print(f"  {DIM}          {w.message}{RESET}")

    print()

    # ── Proposed changes ──
    if result.changeset:
        changes_output = orchestrator.show_changes(result)
        if changes_output and changes_output.strip():
            print(f"  {BOLD}Changes:{RESET}")
            for line in changes_output.strip().split("\n"):
                print(f"    {line}")
            print()

    # ── Code preview — clean, no boxes ──
    if result.generated_code:
        lines = result.generated_code.split("\n")
        preview_count = min(30, len(lines))
        print(f"  {DIM}─── preview ({len(lines)} lines) ───{RESET}")
        for line in lines[:preview_count]:
            print(f"  {DIM}│{RESET} {line}")
        if len(lines) > preview_count:
            print(f"  {DIM}│ ... {len(lines) - preview_count} more lines{RESET}")
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

    # If there's a changeset, handle approval and writing
    if result.changeset and result.changeset.changes:
        if args.yes:
            # Auto-approve all changes
            result.changeset.approve_all()
            safe_writer = SafeCodeWriter(repo_path)
            report = safe_writer.apply_changes(result.changeset)
            _print_write_report(report)
        elif result.changeset.needs_permission:
            # Interactive approval
            _interactive_approval(result.changeset, repo_path)
        else:
            # All changes are safe (new files only) — auto-apply
            result.changeset.approve_all()
            safe_writer = SafeCodeWriter(repo_path)
            report = safe_writer.apply_changes(result.changeset)
            _print_write_report(report)

    # ── POST-WRITE COMMANDS ───────────────────────────────────
    # After files are written, offer to run tests, linting, git push
    post_write = result.context.get("post_write_commands", [])
    if post_write:
        print("  \U0001f4cb Suggested next steps:")
        for i, cmd in enumerate(post_write, 1):
            risk_icons = {"safe": "\u2705", "medium": "\u26a0\ufe0f", "high": "\U0001f534"}
            icon = risk_icons.get(cmd.get("risk", ""), "")
            auto_tag = " (auto-run)" if cmd.get("auto") else ""
            print(f"    {i}. {icon} {cmd['command']}{auto_tag}")
            print(f"       \u2514\u2500 {cmd.get('reason', '')}")
        print()

        try:
            choice = input("  Run suggested commands? [a]ll / [s]afe-only / [n]one: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            choice = "n"

        if choice in ("a", "all", "y", "yes"):
            executor = ShellExecutor(repo_path)
            for cmd in post_write:
                r = executor.run(cmd["command"], auto_approve=True)
                if r.success:
                    print(f"    \u2705 {cmd['command']} \u2014 passed ({r.duration_ms}ms)")
                elif r.blocked_reason:
                    print(f"    \U0001f6ab {cmd['command']} \u2014 blocked: {r.blocked_reason}")
                else:
                    print(f"    \u274c {cmd['command']} \u2014 failed (exit {r.returncode})")
                    if r.stderr:
                        for line in r.stderr.strip().split("\n")[:3]:
                            print(f"       {line[:80]}")
        elif choice in ("s", "safe"):
            executor = ShellExecutor(repo_path)
            for cmd in post_write:
                if cmd.get("risk") == "safe":
                    r = executor.run(cmd["command"], auto_approve=True)
                    if r.success:
                        print(f"    \u2705 {cmd['command']} \u2014 passed ({r.duration_ms}ms)")
                    else:
                        print(f"    \u274c {cmd['command']} \u2014 failed (exit {r.returncode})")
        else:
            print("  Skipped post-write commands.")

    # ── GIT SUGGESTIONS ───────────────────────────────────────
    commit_msg = result.context.get("commit_message", "")
    git_cmds = result.context.get("git_commands", [])
    if commit_msg and git_cmds:
        print("  \U0001f500 Ready to commit:")
        print(f"    git commit -m \"{commit_msg}\"")
        print("    git push origin HEAD")
        print()
        try:
            choice = input("  Push to git? [y/n]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            choice = "n"

        if choice in ("y", "yes"):
            executor = ShellExecutor(repo_path)
            # Add files
            if result.changeset:
                files = [c.file_path for c in result.changeset.changes]
                if files:
                    r = executor.run(f"git add {' '.join(files[:10])}", auto_approve=True)
                    status = "\u2705" if r.success else "\u274c"
                    print(f"    {status} git add")
            # Commit
            r = executor.run(f'git commit -m "{commit_msg}"', auto_approve=True)
            status = "\u2705" if r.success else "\u274c"
            print(f"    {status} git commit")
            # Push
            r = executor.run("git push origin HEAD", auto_approve=True)
            status = "\u2705" if r.success else "\u274c"
            print(f"    {status} git push")
        else:
            print("  Skipped git push.")

    return 0 if result.success else 1


def _interactive_approval(changeset, repo_path: str):
    """Show proposed changes and get user approval before writing."""
    from .safe_writer import SafeCodeWriter

    print()
    print(changeset.to_user_prompt())

    safe = changeset.safe_changes
    needs_approval = changeset.permission_required

    if safe:
        print(f"  \u2705 {len(safe)} new file(s) — auto-approved (safe)")
    if needs_approval:
        print(f"  \u26a0\ufe0f  {len(needs_approval)} file(s) need your approval")
    print()

    # Show each change needing approval
    for i, change in enumerate(needs_approval):
        risk_icons = {"low": "\u26aa", "medium": "\U0001f7e1", "high": "\U0001f7e0", "critical": "\U0001f534"}
        icon = risk_icons.get(change.risk_level.value, "\u26aa")
        print(f"  {icon} [{i+1}] {change.file_path} ({change.risk_level.value} risk)")
        print(f"      {change.description}")
        # Show compact diff (first 8 lines)
        for line in change.diff_lines[:8]:
            if line.startswith('+'):
                print(f"      \033[32m{line}\033[0m")
            elif line.startswith('-'):
                print(f"      \033[31m{line}\033[0m")
            else:
                print(f"      {line}")
        if len(change.diff_lines) > 8:
            print(f"      ... {len(change.diff_lines) - 8} more lines")
        print()

    # Ask for approval
    print("  Options: [a]pprove all | [1,2,3] approve specific | [n]one | [q]uit")
    try:
        choice = input("  > ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\n  Cancelled — no files written.")
        return

    if choice in ('a', 'y', 'yes', 'all'):
        changeset.approve_all()
    elif choice in ('n', 'no', 'none', 'q', 'quit'):
        print("  Skipped — no files written.")
        return
    else:
        # Parse indices: "1,3" or "1 3"
        try:
            indices = [int(x.strip()) - 1 for x in choice.replace(',', ' ').split()]
            # Auto-approve safe changes, plus the selected ones
            for c in changeset.safe_changes:
                c.approved = True
            changeset.approve_by_index(indices)
        except ValueError:
            print("  Invalid input — no files written.")
            return

    # Apply
    safe_writer = SafeCodeWriter(repo_path)
    report = safe_writer.apply_changes(changeset)
    _print_write_report(report)


def _print_write_report(report: dict):
    """Show what was written to disk."""
    print()
    if report.get("applied"):
        print(f"  \u2705 Written {report['total_applied']} file(s):")
        for f in report["applied"]:
            print(f"     \U0001f4c4 {f}")
    if report.get("backed_up"):
        print(f"  \U0001f4be {len(report['backed_up'])} backup(s) created")
    if report.get("skipped") and report["total_skipped"] > 0:
        print(f"  \u23ed\ufe0f  Skipped {report['total_skipped']} file(s)")
    if report.get("errors"):
        print("  \u274c Errors:")
        for e in report["errors"]:
            print(f"     {e}")
    print()


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
        try:
            exit_code = asyncio.run(interactive_session(args))
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n  Session ended.")
            exit_code = 0
        sys.exit(exit_code)

    # Single-shot mode requires a request
    if not args.request:
        parser.print_help()
        sys.exit(1)

    try:
        exit_code = asyncio.run(run(args))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n  Interrupted.")
        exit_code = 130
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
