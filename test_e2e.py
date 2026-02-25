"""
End-to-End Pipeline Test — Contextual Architect

Tests the REAL pipeline against REAL projects with a REAL LLM.
This is the first true integration test.

Usage:
    # Set your API key first:
    #   $env:GOOGLE_API_KEY = "your-key-here"
    
    # Run all tests:
    python test_e2e.py
    
    # Run specific project:
    python test_e2e.py --project my-api
    
    # Dry run (no files written):
    python test_e2e.py --dry-run
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.orchestrator import Orchestrator
from agents.config import AgentConfig
from agents.llm_client import create_llm_client, detect_provider_from_env


# ── Test Cases ──────────────────────────────────────────

@dataclass
class TestCase:
    """A single end-to-end test scenario."""
    project_dir: str
    request: str
    language: str
    description: str


TEST_CASES = [
    TestCase(
        project_dir="my-api",
        request="Add a health check endpoint at /health that returns JSON with status and uptime",
        language="python",
        description="Tiny Flask app (3 files) — simplest possible test",
    ),
    TestCase(
        project_dir="fastapi-app",
        request="Add rate limiting middleware to protect API endpoints",
        language="python",
        description="FastAPI project — checks if agent detects async patterns",
    ),
    TestCase(
        project_dir="flask-project",
        request="Add a /metrics endpoint that returns request count and average response time",
        language="python",
        description="Flask project — checks style matching",
    ),
    TestCase(
        project_dir="django-project",
        request="Add a simple health check view at /health/",
        language="python",
        description="Django project (7K files) — stress test on large codebase",
    ),
    TestCase(
        project_dir="express-project",
        request="Add an error handling middleware that logs errors and returns JSON error responses",
        language="javascript",
        description="Express.js project — cross-language test",
    ),
    TestCase(
        project_dir="click-project",
        request="Add a --verbose flag that enables debug logging across all commands",
        language="python",
        description="Click CLI library — library-style project",
    ),
    TestCase(
        project_dir="httpie",
        request="Add a --timeout flag to set request timeout in seconds",
        language="python",
        description="HTTPie — real-world open source tool",
    ),
    TestCase(
        project_dir="requests-lib",
        request="Add retry logic with exponential backoff for failed requests",
        language="python",
        description="Requests library — widely-known project",
    ),
    TestCase(
        project_dir="X-rayProject",
        request="Add DICOM (.dcm) image format support using pydicom",
        language="python",
        description="Medical AI project — single file, domain-specific",
    ),
    TestCase(
        project_dir="empty-project",
        request="Create a basic Flask API with a hello world endpoint",
        language="python",
        description="Empty project — tests greenfield generation",
    ),
]


# ── Test Results ────────────────────────────────────────

@dataclass
class TestResult:
    """Result of a single test run."""
    test_case: TestCase
    success: bool
    duration_seconds: float
    code_generated: str = ""
    errors: List[str] = field(default_factory=list)
    tokens_used: dict = field(default_factory=dict)
    agent_outputs: dict = field(default_factory=dict)


# ── Runner ──────────────────────────────────────────────

async def run_single_test(
    test_case: TestCase,
    test_projects_root: str,
    llm_client,
    config: AgentConfig,
    dry_run: bool = True,
) -> TestResult:
    """Run a single end-to-end test."""
    
    repo_path = os.path.join(test_projects_root, test_case.project_dir)
    
    if not os.path.isdir(repo_path):
        return TestResult(
            test_case=test_case,
            success=False,
            duration_seconds=0,
            errors=[f"Project directory not found: {repo_path}"],
        )
    
    print(f"\n{'='*60}")
    print(f"  TEST: {test_case.project_dir}")
    print(f"  Request: {test_case.request}")
    print(f"  {test_case.description}")
    print(f"{'='*60}")
    
    orchestrator = Orchestrator(llm_client=llm_client, config=config)
    
    start = time.time()
    try:
        result = await orchestrator.run(
            user_request=test_case.request,
            repo_path=repo_path,
            language=test_case.language,
        )
        duration = time.time() - start
        
        # Extract code from result
        code = result.generated_code or ""
        
        return TestResult(
            test_case=test_case,
            success=result.success,
            duration_seconds=duration,
            code_generated=code,
            errors=result.errors or [],
            tokens_used=getattr(result, "token_usage", {}),
        )
        
    except Exception as e:
        duration = time.time() - start
        import traceback
        return TestResult(
            test_case=test_case,
            success=False,
            duration_seconds=duration,
            errors=[f"Pipeline exception: {e}\n{traceback.format_exc()}"],
        )


def print_summary(results: List[TestResult]):
    """Print a summary table of all test results."""
    
    print(f"\n\n{'='*70}")
    print("  END-TO-END TEST RESULTS")
    print(f"{'='*70}\n")
    
    passed = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    total_time = sum(r.duration_seconds for r in results)
    
    print(f"  {'Project':<20} {'Status':<10} {'Time':<10} {'Code Lines':<12} {'Errors'}")
    print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*12} {'-'*20}")
    
    for r in results:
        status = "✅ PASS" if r.success else "❌ FAIL"
        time_str = f"{r.duration_seconds:.1f}s"
        code_lines = len(r.code_generated.splitlines()) if r.code_generated else 0
        errors = r.errors[0][:40] if r.errors else "-"
        
        print(f"  {r.test_case.project_dir:<20} {status:<10} {time_str:<10} {code_lines:<12} {errors}")
    
    print(f"\n  Total: {passed} passed, {failed} failed, {total_time:.1f}s total")
    print()
    
    # Write detailed results to file
    output_dir = Path("E:/FUn/test-projects/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    report = output_dir / "e2e_report.md"
    with open(report, "w", encoding="utf-8") as f:
        f.write("# End-to-End Test Report\n\n")
        f.write(f"**Date**: {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Results**: {passed}/{passed+failed} passed\n")
        f.write(f"**Total Time**: {total_time:.1f}s\n\n")
        
        for r in results:
            status = "✅ PASS" if r.success else "❌ FAIL"
            f.write(f"## {r.test_case.project_dir} — {status}\n\n")
            f.write(f"- **Request**: {r.test_case.request}\n")
            f.write(f"- **Time**: {r.duration_seconds:.1f}s\n")
            
            if r.errors:
                f.write(f"- **Errors**:\n")
                for err in r.errors:
                    f.write(f"  - {err[:200]}\n")
            
            if r.code_generated:
                f.write(f"\n### Generated Code\n\n```{r.test_case.language}\n")
                # Limit to first 100 lines
                lines = r.code_generated.splitlines()
                f.write("\n".join(lines[:100]))
                if len(lines) > 100:
                    f.write(f"\n# ... ({len(lines) - 100} more lines)")
                f.write("\n```\n\n")
            
            f.write("---\n\n")
    
    print(f"  📄 Detailed report saved to: {report}")


# ── API Key Check ───────────────────────────────────────

def verify_api_connection(provider: str, api_key: Optional[str]) -> bool:
    """Quick smoke test: can we reach the LLM API?"""
    
    print("\n🔑 Verifying LLM connection...")
    print(f"   Provider: {provider}")
    print(f"   Key set: {'Yes' if api_key else 'NO ❌'}")
    
    if not api_key and provider not in ("ollama", "mock"):
        print("\n❌ No API key found!")
        print("   Set one of these environment variables:\n")
        print("   PowerShell:")
        print('     $env:GOOGLE_API_KEY = "your-key-here"')
        print("     # or")
        print('     $env:DEEPSEEK_API_KEY = "your-key-here"')
        print()
        return False
    
    if provider == "mock":
        print("   ⚠️  Using MOCK client (no real LLM). Results will be placeholder text.")
        print("   Set an API key to use a real LLM.\n")
        return True  # Still allow running with mock
    
    try:
        client = create_llm_client(provider=provider, api_key=api_key)
        print(f"   Model: {client.model_name}")
        
        # Quick test call
        response = asyncio.run(_quick_test(client))
        print(f"   ✅ Connection successful! Response: {response[:60]}...")
        return True
        
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return False


async def _quick_test(client) -> str:
    """Send a minimal test prompt."""
    resp = await client.generate(
        system_prompt="You are a helpful assistant.",
        user_prompt="Reply with exactly: CONNECTED",
        temperature=0.0,
        max_tokens=20,
    )
    return resp.content


# ── Main ────────────────────────────────────────────────

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="E2E Pipeline Test")
    parser.add_argument("--project", help="Test specific project only")
    parser.add_argument("--dry-run", action="store_true", help="Don't write files")
    parser.add_argument("--mock", action="store_true", help="Use mock LLM (no API key needed)")
    parser.add_argument("--provider", help="Force LLM provider")
    parser.add_argument("--api-key", help="API key override")
    parser.add_argument("--skip-verify", action="store_true", help="Skip API verification")
    args = parser.parse_args()
    
    test_projects_root = "E:/FUn/test-projects"
    
    # Determine provider
    if args.mock:
        provider, api_key = "mock", None
    elif args.provider:
        provider = args.provider
        api_key = args.api_key or os.environ.get(
            {"google": "GOOGLE_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
             "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider, ""),
        )
    else:
        provider, api_key = detect_provider_from_env()
    
    # Verify connection
    if not args.skip_verify:
        if not verify_api_connection(provider, api_key):
            sys.exit(1)
    
    # Create LLM client
    try:
        llm_client = create_llm_client(provider=provider, api_key=api_key)
    except Exception as e:
        print(f"❌ Cannot create LLM client: {e}")
        sys.exit(1)
    
    # Build config
    config = AgentConfig(
        llm_provider=provider,
        llm_api_key=api_key,
        max_retries=1,  # Keep retries low for testing
    )
    
    # Filter test cases
    if args.project:
        cases = [tc for tc in TEST_CASES if tc.project_dir == args.project]
        if not cases:
            print(f"❌ Unknown project: {args.project}")
            print(f"   Available: {', '.join(tc.project_dir for tc in TEST_CASES)}")
            sys.exit(1)
    else:
        cases = TEST_CASES
    
    print(f"\n🏗️  Contextual Architect — End-to-End Test")
    print(f"   Projects: {len(cases)}")
    print(f"   Provider: {provider} ({llm_client.model_name})")
    print(f"   Dry run: {args.dry_run}")
    
    # Run tests
    results = []
    for case in cases:
        result = asyncio.run(
            run_single_test(case, test_projects_root, llm_client, config, args.dry_run)
        )
        results.append(result)
        
        # Print quick status
        if result.success:
            lines = len(result.code_generated.splitlines()) if result.code_generated else 0
            print(f"  ✅ {case.project_dir}: {lines} lines in {result.duration_seconds:.1f}s")
        else:
            print(f"  ❌ {case.project_dir}: {result.errors[0][:80] if result.errors else 'Unknown error'}")
    
    # Print summary
    print_summary(results)


if __name__ == "__main__":
    main()
