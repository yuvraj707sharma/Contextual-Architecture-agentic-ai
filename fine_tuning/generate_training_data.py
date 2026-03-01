"""
Generate synthetic training data by running MACRO's pipeline with a
powerful LLM (Gemini/GPT-4o) on sample tasks.

This creates the (input, plan, output) pairs needed for distillation.

Usage:
    python generate_training_data.py --provider google --num-tasks 30
    python generate_training_data.py --provider groq --num-tasks 10 --repo /path/to/repo
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add parent dir to path so we can import agents
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.config import AgentConfig
from agents.llm_client import create_llm_client
from agents.orchestrator import Orchestrator
from fine_tuning.sample_tasks import SAMPLE_TASKS


def find_sample_repo() -> str:
    """Find a sample repo to run tasks against."""
    # Use the contextual-architect repo itself as the sample
    repo = Path(__file__).parent.parent
    if (repo / "agents").is_dir():
        return str(repo)
    return "."


async def generate_one(
    task: dict,
    orchestrator: Orchestrator,
    repo_path: str,
    task_idx: int,
    total: int,
) -> dict:
    """Run a single task through the pipeline and capture the trace."""
    request = task["request"]
    language = task["language"]
    
    print(f"  [{task_idx}/{total}] {request[:60]}...", end=" ", flush=True)
    start = time.perf_counter()
    
    try:
        result = await orchestrator.run(
            user_request=request,
            repo_path=repo_path,
            language=language,
        )
        
        elapsed = time.perf_counter() - start
        
        if result.success:
            print(f"OK ({elapsed:.1f}s, {len(result.generated_code)} chars)")
        else:
            print(f"FAILED ({elapsed:.1f}s)")
        
        # Build training record
        record = {
            "task": request,
            "language": language,
            "expected_complexity": task["complexity"],
            "success": result.success,
            "attempts": result.attempts,
            "generated_code_len": len(result.generated_code),
            "elapsed_seconds": round(elapsed, 2),
            "agent_summaries": result.agent_summaries,
            "context": {
                "historian": result.context.get("historian", {}),
                "architect": result.context.get("architect", {}),
                "style": result.context.get("style", {}),
            },
            "generated_code": result.generated_code,
            "target_file": result.target_file,
            "errors": result.errors,
        }
        
        # Add validation details if available
        if result.validation:
            record["validation"] = {
                "passed": result.validation.passed,
                "summary": result.validation.summary,
            }
        
        return record
        
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"ERROR: {e} ({elapsed:.1f}s)")
        return {
            "task": request,
            "language": language,
            "success": False,
            "error": str(e),
            "elapsed_seconds": round(elapsed, 2),
        }


async def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic training data for MACRO distillation"
    )
    parser.add_argument(
        "--provider", "-p",
        default="google",
        choices=["google", "groq", "openai", "anthropic", "deepseek"],
        help="LLM provider to use as teacher model (default: google)",
    )
    parser.add_argument(
        "--num-tasks", "-n",
        type=int,
        default=30,
        help="Number of tasks to run (default: 30, max: all sample tasks)",
    )
    parser.add_argument(
        "--repo", "-r",
        type=str,
        default=None,
        help="Repository to run tasks against (default: contextual-architect itself)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="data/raw_traces.jsonl",
        help="Output JSONL file (default: data/raw_traces.jsonl)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key (alternative to environment variable)",
    )
    
    args = parser.parse_args()
    
    # Setup
    repo_path = args.repo or find_sample_repo()
    
    print()
    print("  MACRO Training Data Generator")
    print("  " + "=" * 40)
    print(f"  Provider:  {args.provider}")
    print(f"  Repo:      {repo_path}")
    print(f"  Tasks:     {args.num_tasks}")
    print(f"  Output:    {args.output}")
    print()
    
    # Create LLM client
    try:
        llm_client = create_llm_client(
            provider=args.provider,
            api_key=args.api_key,
        )
    except ValueError as e:
        print(f"  [X] Failed to create LLM client: {e}")
        print(f"      Set your API key: export GOOGLE_API_KEY=your_key")
        sys.exit(1)
    
    # Create orchestrator
    config = AgentConfig.load_user_config()
    config.llm_provider = args.provider
    if args.api_key:
        config.llm_api_key = args.api_key
    
    orchestrator = Orchestrator(llm_client=llm_client, config=config, repo_path=repo_path)
    
    # Select tasks
    tasks = SAMPLE_TASKS[:args.num_tasks]
    total = len(tasks)
    
    print(f"  Running {total} tasks...")
    print()
    
    # Output directory
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Run tasks sequentially (to avoid rate limiting)
    results = []
    successful = 0
    
    for i, task in enumerate(tasks, 1):
        record = await generate_one(task, orchestrator, repo_path, i, total)
        results.append(record)
        
        if record.get("success"):
            successful += 1
        
        # Save after each task (in case of crash)
        with open(output_path, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, default=str) + "\n")
        
        # Small delay to avoid rate limiting
        if i < total:
            await asyncio.sleep(2)
    
    # Summary
    print()
    print("  " + "=" * 40)
    print(f"  Done! {successful}/{total} tasks succeeded")
    print(f"  Output: {output_path}")
    print(f"  Next: python format_dataset.py --input {args.output}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
