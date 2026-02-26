"""
GitHub PR Evaluator for Contextual Architect.

Fetches real PRs from GitHub, clones the repo at pre-PR state,
runs the pipeline, and compares output against the actual PR diff.

Usage:
    python pr_evaluator.py --repo owner/repo --pr 42 --provider groq
    python pr_evaluator.py --repo owner/repo --prs 10,15,22 --provider groq

Requires:
    GITHUB_TOKEN env var (for private repos and higher rate limits)
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ─── Data Classes ─────────────────────────────────────────────

@dataclass
class PRData:
    """Extracted PR metadata."""
    owner: str
    repo: str
    number: int
    title: str
    body: str
    base_sha: str
    head_sha: str
    clone_url: str
    changed_files: List[Dict[str, str]] = field(default_factory=list)
    diff_text: str = ""
    language: str = "python"


@dataclass
class ComparisonResult:
    """Result of comparing generated code against actual PR."""
    pr_number: int
    pr_title: str
    # Pipeline results
    pipeline_success: bool
    generated_code: str = ""
    target_file: str = ""
    pipeline_time_ms: float = 0.0
    attempts: int = 0
    # Comparison metrics
    file_target_match: bool = False
    pattern_similarity: float = 0.0
    security_passed: bool = False
    convention_score: float = 0.0
    # Actual PR data
    actual_files_changed: List[str] = field(default_factory=list)
    actual_diff_snippet: str = ""
    # Errors
    errors: List[str] = field(default_factory=list)
    agent_summaries: Dict[str, str] = field(default_factory=dict)


# ─── GitHub API ───────────────────────────────────────────────

def github_api(endpoint: str, token: Optional[str] = None, accept: str = "application/vnd.github.v3+json") -> Any:
    """Make a GitHub API request."""
    url = f"https://api.github.com{endpoint}"
    headers = {"Accept": accept, "User-Agent": "contextual-architect-evaluator"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    req = Request(url, headers=headers)
    try:
        with urlopen(req) as resp:
            if accept == "application/vnd.github.v3.diff":
                return resp.read().decode("utf-8", errors="replace")
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API error {e.code}: {body}") from e


def fetch_pr_data(owner: str, repo: str, pr_number: int, token: Optional[str] = None) -> PRData:
    """Fetch all PR metadata from GitHub API."""
    print(f"\n  [1/4] Fetching PR #{pr_number} from {owner}/{repo}...")
    
    # Get PR metadata
    pr = github_api(f"/repos/{owner}/{repo}/pulls/{pr_number}", token)
    
    # Get changed files
    files = github_api(f"/repos/{owner}/{repo}/pulls/{pr_number}/files", token)
    changed_files = [
        {"filename": f["filename"], "status": f["status"], "additions": f["additions"], "deletions": f["deletions"]}
        for f in files
    ]
    
    # Get diff
    diff_text = github_api(
        f"/repos/{owner}/{repo}/pulls/{pr_number}",
        token,
        accept="application/vnd.github.v3.diff"
    )
    
    # Detect primary language from file extensions
    extensions = [Path(f["filename"]).suffix for f in files]
    lang_map = {".py": "python", ".js": "javascript", ".ts": "typescript", ".go": "go", ".java": "java", ".rs": "rust", ".cpp": "cpp", ".c": "c"}
    language = "python"  # default
    for ext in extensions:
        if ext in lang_map:
            language = lang_map[ext]
            break
    
    # Determine clone URL (use token for private repos)
    clone_url = pr["base"]["repo"]["clone_url"]
    if token and pr["base"]["repo"].get("private"):
        # Embed token in URL for private repo cloning
        clone_url = clone_url.replace("https://", f"https://x-access-token:{token}@")
    
    pr_data = PRData(
        owner=owner,
        repo=repo,
        number=pr_number,
        title=pr["title"],
        body=pr.get("body") or "",
        base_sha=pr["base"]["sha"],
        head_sha=pr["head"]["sha"],
        clone_url=clone_url,
        changed_files=changed_files,
        diff_text=diff_text,
        language=language,
    )
    
    print(f"       Title: {pr_data.title}")
    print(f"       Files changed: {len(changed_files)}")
    print(f"       Language: {language}")
    print(f"       Base SHA: {pr_data.base_sha[:8]}")
    
    return pr_data


# ─── Repo Cloning ─────────────────────────────────────────────

def clone_at_base(pr_data: PRData, temp_dir: str) -> str:
    """Clone the repo and checkout at the base (pre-PR) commit."""
    print(f"\n  [2/4] Cloning {pr_data.owner}/{pr_data.repo} at pre-PR state...")
    
    repo_dir = os.path.join(temp_dir, pr_data.repo)
    
    # Clone with enough depth to reach the base commit
    result = subprocess.run(
        ["git", "clone", "--depth", "200", pr_data.clone_url, repo_dir],
        capture_output=True, text=True, timeout=120
    )
    
    if result.returncode != 0:
        # Try without depth limit for older commits
        print("       Shallow clone failed, trying full clone...")
        result = subprocess.run(
            ["git", "clone", pr_data.clone_url, repo_dir],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git clone failed: {result.stderr}")
    
    # Checkout base commit (the state BEFORE the PR)
    result = subprocess.run(
        ["git", "checkout", pr_data.base_sha],
        capture_output=True, text=True, cwd=repo_dir
    )
    
    if result.returncode != 0:
        # Fetch the specific commit if not in shallow clone
        subprocess.run(
            ["git", "fetch", "origin", pr_data.base_sha],
            capture_output=True, text=True, cwd=repo_dir
        )
        result = subprocess.run(
            ["git", "checkout", pr_data.base_sha],
            capture_output=True, text=True, cwd=repo_dir
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git checkout failed: {result.stderr}")
    
    # Count files in repo
    file_count = sum(1 for _ in Path(repo_dir).rglob("*") if _.is_file() and ".git" not in str(_))
    print(f"       Cloned to: {repo_dir}")
    print(f"       Files in repo: {file_count}")
    print(f"       State: pre-PR (base commit {pr_data.base_sha[:8]})")
    
    return repo_dir


# ─── Pipeline Execution ──────────────────────────────────────

async def run_pipeline(repo_path: str, pr_data: PRData, provider: str, api_key: Optional[str] = None):
    """Run Contextual Architect pipeline on the cloned repo."""
    from agents.orchestrator import Orchestrator
    from agents.llm_client import create_llm_client
    
    print(f"\n  [3/4] Running Contextual Architect pipeline...")
    
    # Build the task description from PR title + body
    task = pr_data.title
    if pr_data.body and len(pr_data.body.strip()) > 10:
        # Use first 500 chars of PR body as additional context
        body_clean = pr_data.body.strip()[:500]
        task = f"{pr_data.title}\n\nDetails: {body_clean}"
    
    print(f"       Task: {task[:100]}...")
    print(f"       Provider: {provider}")
    print(f"       Language: {pr_data.language}")
    
    # Create LLM client
    llm_client = create_llm_client(provider=provider, api_key=api_key)
    print(f"       Model: {llm_client.model_name}")
    
    # Create orchestrator with RAG
    orchestrator = Orchestrator(llm_client=llm_client, repo_path=repo_path)
    
    # Run pipeline
    start = time.perf_counter()
    result = await orchestrator.run(
        user_request=task,
        repo_path=repo_path,
        language=pr_data.language,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    status = "[PASS]" if result.success else "[FAIL]"
    print(f"       {status} Pipeline completed in {elapsed_ms:.0f}ms ({result.attempts} attempt(s))")
    print(f"       Target file: {result.target_file}")
    print(f"       Generated code: {len(result.generated_code)} chars")
    
    return result, elapsed_ms


# ─── Comparison Engine ────────────────────────────────────────

def extract_identifiers(code: str) -> set:
    """Extract function names, class names, and imports from code."""
    identifiers = set()
    
    # Function/method definitions
    for match in re.finditer(r'def\s+(\w+)', code):
        identifiers.add(match.group(1))
    
    # Class definitions
    for match in re.finditer(r'class\s+(\w+)', code):
        identifiers.add(match.group(1))
    
    # Import names
    for match in re.finditer(r'(?:from\s+\S+\s+)?import\s+(.+)', code):
        for name in match.group(1).split(','):
            name = name.strip().split(' as ')[0].strip()
            if name and name != '*':
                identifiers.add(name.split('.')[-1])
    
    return identifiers


def compare_output(pr_data: PRData, generated_code: str, target_file: str) -> Dict[str, Any]:
    """Compare generated code against the actual PR diff."""
    print(f"\n  [4/4] Comparing against actual PR diff...")
    
    actual_files = [f["filename"] for f in pr_data.changed_files]
    
    # 1. File target match
    target_basename = os.path.basename(target_file) if target_file else ""
    actual_basenames = [os.path.basename(f) for f in actual_files]
    file_match = target_basename in actual_basenames
    
    # Also check partial path match
    path_match = any(
        target_file and (f in target_file or target_file.endswith(f))
        for f in actual_files
    )
    
    print(f"       File match: {'YES' if (file_match or path_match) else 'NO'}")
    print(f"         Generated target: {target_file}")
    print(f"         Actual PR files: {actual_files}")
    
    # 2. Pattern similarity (Jaccard on identifiers)
    generated_ids = extract_identifiers(generated_code)
    
    # Extract identifiers from diff (additions only)
    diff_additions = "\n".join(
        line[1:] for line in pr_data.diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    actual_ids = extract_identifiers(diff_additions)
    
    if generated_ids and actual_ids:
        intersection = generated_ids & actual_ids
        union = generated_ids | actual_ids
        jaccard = len(intersection) / len(union) if union else 0.0
    else:
        jaccard = 0.0
        intersection = set()
    
    print(f"       Pattern similarity: {jaccard:.1%}")
    print(f"         Shared identifiers: {intersection or 'none'}")
    print(f"         Generated: {generated_ids}")
    print(f"         Actual PR: {actual_ids}")
    
    # 3. Security check (CWE denylist)
    security_issues = []
    security_patterns = [
        (r'\beval\s*\(', "CWE-502: eval() usage"),
        (r'\bexec\s*\(', "CWE-502: exec() usage"),
        (r'os\.system\s*\(', "CWE-78: os.system() usage"),
        (r'subprocess.*shell\s*=\s*True', "CWE-78: subprocess shell=True"),
        (r'except\s*:', "Bare except clause"),
    ]
    for pattern, desc in security_patterns:
        if re.search(pattern, generated_code):
            security_issues.append(desc)
    
    security_passed = len(security_issues) == 0
    print(f"       Security: {'PASS' if security_passed else 'FAIL'}")
    if security_issues:
        for issue in security_issues:
            print(f"         [WARN] {issue}")
    
    # 4. Convention score (naming, structure)
    convention_checks = 0
    convention_passed = 0
    
    # Check snake_case functions
    functions = re.findall(r'def\s+(\w+)', generated_code)
    if functions:
        convention_checks += 1
        snake_case = all(f == f.lower() or f.startswith('_') for f in functions)
        if snake_case:
            convention_passed += 1
    
    # Check has docstrings
    if 'def ' in generated_code:
        convention_checks += 1
        if '"""' in generated_code or "'''" in generated_code:
            convention_passed += 1
    
    # Check has type hints
    if 'def ' in generated_code:
        convention_checks += 1
        if '->' in generated_code or ': ' in generated_code:
            convention_passed += 1
    
    convention_score = convention_passed / convention_checks if convention_checks > 0 else 0.0
    print(f"       Convention score: {convention_score:.0%} ({convention_passed}/{convention_checks})")
    
    return {
        "file_target_match": file_match or path_match,
        "pattern_similarity": round(jaccard, 3),
        "security_passed": security_passed,
        "security_issues": security_issues,
        "convention_score": round(convention_score, 3),
        "shared_identifiers": list(intersection),
        "generated_identifiers": list(generated_ids),
        "actual_identifiers": list(actual_ids),
    }


# ─── Main Evaluation ─────────────────────────────────────────

async def evaluate_pr(
    owner: str,
    repo: str,
    pr_number: int,
    provider: str,
    api_key: Optional[str] = None,
    token: Optional[str] = None,
) -> ComparisonResult:
    """Full PR evaluation: fetch → clone → run → compare."""
    
    print(f"\n{'=' * 70}")
    print(f"  PR EVALUATION: {owner}/{repo} #{pr_number}")
    print(f"{'=' * 70}")
    
    temp_dir = tempfile.mkdtemp(prefix="ca-eval-")
    
    try:
        # 1. Fetch PR data
        pr_data = fetch_pr_data(owner, repo, pr_number, token)
        
        # 2. Clone at base
        repo_path = clone_at_base(pr_data, temp_dir)
        
        # 3. Run pipeline
        result, elapsed_ms = await run_pipeline(repo_path, pr_data, provider, api_key)
        
        # 4. Compare
        comparison = compare_output(pr_data, result.generated_code, result.target_file)
        
        return ComparisonResult(
            pr_number=pr_number,
            pr_title=pr_data.title,
            pipeline_success=result.success,
            generated_code=result.generated_code,
            target_file=result.target_file,
            pipeline_time_ms=elapsed_ms,
            attempts=result.attempts,
            file_target_match=comparison["file_target_match"],
            pattern_similarity=comparison["pattern_similarity"],
            security_passed=comparison["security_passed"],
            convention_score=comparison["convention_score"],
            actual_files_changed=[f["filename"] for f in pr_data.changed_files],
            actual_diff_snippet=pr_data.diff_text[:1000],
            agent_summaries=result.agent_summaries,
        )
    
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        import traceback
        traceback.print_exc()
        return ComparisonResult(
            pr_number=pr_number,
            pr_title=f"Error fetching PR #{pr_number}",
            pipeline_success=False,
            errors=[str(e)],
        )
    
    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


# ─── Output ───────────────────────────────────────────────────

def print_scorecard(results: List[ComparisonResult]):
    """Print human-readable scorecard."""
    print(f"\n{'=' * 70}")
    print(f"  PR EVALUATION SCORECARD")
    print(f"{'=' * 70}")
    
    for r in results:
        status = "[PASS]" if r.pipeline_success else "[FAIL]"
        print(f"\n  {status} PR #{r.pr_number}: {r.pr_title}")
        print(f"    Time: {r.pipeline_time_ms:.0f}ms | Attempts: {r.attempts}")
        print(f"    File target match:   {'YES' if r.file_target_match else 'NO'}")
        print(f"    Pattern similarity:  {r.pattern_similarity:.1%}")
        print(f"    Security compliant:  {'YES' if r.security_passed else 'NO'}")
        print(f"    Convention score:    {r.convention_score:.0%}")
        print(f"    Actual files:        {r.actual_files_changed}")
        print(f"    Generated target:    {r.target_file}")
        if r.errors:
            print(f"    Errors: {r.errors}")
    
    # Summary
    total = len(results)
    if total > 0:
        pipeline_pass = sum(1 for r in results if r.pipeline_success)
        file_match = sum(1 for r in results if r.file_target_match)
        security_pass = sum(1 for r in results if r.security_passed)
        avg_similarity = sum(r.pattern_similarity for r in results) / total
        avg_convention = sum(r.convention_score for r in results) / total
        avg_time = sum(r.pipeline_time_ms for r in results) / total
        
        print(f"\n  {'─' * 50}")
        print(f"  SUMMARY ({total} PRs evaluated)")
        print(f"  {'─' * 50}")
        print(f"    Pipeline success rate:  {pipeline_pass}/{total} ({pipeline_pass/total:.0%})")
        print(f"    File target match:      {file_match}/{total} ({file_match/total:.0%})")
        print(f"    Security compliance:    {security_pass}/{total} ({security_pass/total:.0%})")
        print(f"    Avg pattern similarity: {avg_similarity:.1%}")
        print(f"    Avg convention score:   {avg_convention:.0%}")
        print(f"    Avg pipeline time:      {avg_time:.0f}ms")


def save_results(results: List[ComparisonResult], output_dir: str = "evaluation_results"):
    """Save PR evaluation results to JSON."""
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(output_dir, f"pr_eval_{timestamp}.json")
    
    data = {
        "timestamp": timestamp,
        "total_prs": len(results),
        "results": [asdict(r) for r in results],
        "summary": {
            "pipeline_success_rate": sum(1 for r in results if r.pipeline_success) / len(results) if results else 0,
            "file_match_rate": sum(1 for r in results if r.file_target_match) / len(results) if results else 0,
            "security_compliance_rate": sum(1 for r in results if r.security_passed) / len(results) if results else 0,
            "avg_pattern_similarity": sum(r.pattern_similarity for r in results) / len(results) if results else 0,
        }
    }
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f"\n  Results saved to: {filename}")
    return filename


# ─── CLI ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate Contextual Architect against real GitHub PRs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pr_evaluator.py --repo tiangolo/fastapi --pr 42 --provider groq
  python pr_evaluator.py --repo owner/repo --prs 10,15,22 --provider groq
  python pr_evaluator.py --repo owner/private-repo --pr 5 --provider groq

Environment variables:
  GITHUB_TOKEN   GitHub personal access token (required for private repos)
  GROQ_API_KEY   Groq API key (if using --provider groq)
        """
    )
    parser.add_argument("--repo", required=True, help="GitHub repo (owner/repo)")
    parser.add_argument("--pr", type=int, help="Single PR number")
    parser.add_argument("--prs", help="Comma-separated PR numbers (e.g., 10,15,22)")
    parser.add_argument("--provider", default="groq", help="LLM provider (default: groq)")
    parser.add_argument("--api-key", help="LLM API key (or use env var)")
    parser.add_argument("--delay", type=int, default=5, help="Delay between PRs in seconds (default: 5)")
    parser.add_argument("--output-dir", default="evaluation_results", help="Output directory")
    
    args = parser.parse_args()
    
    # Parse repo
    parts = args.repo.split("/")
    if len(parts) != 2:
        print("Error: --repo must be in format 'owner/repo'")
        sys.exit(1)
    owner, repo = parts
    
    # Parse PR numbers
    pr_numbers = []
    if args.pr:
        pr_numbers = [args.pr]
    elif args.prs:
        pr_numbers = [int(n.strip()) for n in args.prs.split(",")]
    else:
        print("Error: must specify --pr or --prs")
        sys.exit(1)
    
    # Get GitHub token
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("[WARN] No GITHUB_TOKEN set. Private repos will fail and rate limits are lower.")
    
    print(f"\n  Contextual Architect — PR Evaluator")
    print(f"  Repo: {owner}/{repo}")
    print(f"  PRs: {pr_numbers}")
    print(f"  Provider: {args.provider}")
    print(f"  GitHub token: {'set' if token else 'NOT SET'}")
    
    # Run evaluations
    results = []
    for i, pr_num in enumerate(pr_numbers):
        if i > 0:
            print(f"\n  Waiting {args.delay}s before next PR...")
            time.sleep(args.delay)
        
        result = asyncio.run(evaluate_pr(
            owner=owner,
            repo=repo,
            pr_number=pr_num,
            provider=args.provider,
            api_key=args.api_key,
            token=token,
        ))
        results.append(result)
    
    # Print scorecard
    print_scorecard(results)
    
    # Save results
    save_results(results, args.output_dir)


if __name__ == "__main__":
    main()
