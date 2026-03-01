"""
Format raw MACRO traces into training data for QLoRA fine-tuning.

Converts raw_traces.jsonl -> train.jsonl in ChatML format compatible
with Qwen2.5-Coder and other instruction-tuned models.

Usage:
    python format_dataset.py --input data/raw_traces.jsonl --output data/train.jsonl
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any


def format_planner_example(record: dict) -> dict:
    """Create a Planner training example from a trace record.
    
    Teaches the model: given a user request + repo context,
    produce a structured plan.
    """
    # Build the input context (what the Planner sees)
    context_parts = []
    
    # Historian summary
    historian = record.get("agent_summaries", {}).get("historian", "")
    if historian:
        context_parts.append(f"## Repository Analysis\n{historian}")
    
    # Architect summary
    architect = record.get("agent_summaries", {}).get("architect", "")
    if architect:
        context_parts.append(f"## Architecture\n{architect}")
    
    # Style info
    style = record.get("context", {}).get("style", {})
    if style:
        style_str = ", ".join(f"{k}: {v}" for k, v in style.items() if v)
        context_parts.append(f"## Code Style\n{style_str}")
    
    context = "\n\n".join(context_parts) if context_parts else "No prior context available."
    
    # Build the expected output (what the Planner should produce)
    planner_summary = record.get("agent_summaries", {}).get("planner", "")
    
    # The Planner's structured output
    plan_output = {
        "task": record["task"],
        "complexity": record.get("expected_complexity", "medium"),
        "target_file": record.get("target_file", ""),
        "plan_summary": planner_summary,
        "success": record.get("success", False),
    }
    
    return {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a code planning agent within the MACRO pipeline. "
                    "Given a user's coding request and repository context from "
                    "the Historian and Architect agents, produce a structured plan "
                    "with acceptance criteria, target files, and complexity assessment. "
                    "Your plan will be used by the Implementer agent to generate code."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## User Request\n{record['task']}\n\n"
                    f"## Language\n{record.get('language', 'python')}\n\n"
                    f"## Repository Context\n{context}"
                ),
            },
            {
                "role": "assistant",
                "content": json.dumps(plan_output, indent=2),
            },
        ]
    }


def format_implementer_example(record: dict) -> dict:
    """Create an Implementer training example from a trace record.
    
    Teaches the model: given a plan + context, produce code that
    follows the project's conventions.
    """
    if not record.get("generated_code"):
        return None
    
    # Build input
    planner_summary = record.get("agent_summaries", {}).get("planner", "")
    style = record.get("context", {}).get("style", {})
    style_str = ", ".join(f"{k}: {v}" for k, v in style.items() if v) if style else "default"
    
    return {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a code implementation agent within the MACRO pipeline. "
                    "Given a structured plan from the Planner agent and style guidelines "
                    "from the Style Analyzer, generate production-grade code that follows "
                    "the project's conventions. Your code will be reviewed by the Reviewer "
                    "agent for syntax, security (CWE denylist), and linting compliance."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## Plan\n{planner_summary}\n\n"
                    f"## Target File\n{record.get('target_file', 'new_file')}\n\n"
                    f"## Language\n{record.get('language', 'python')}\n\n"
                    f"## Style Guidelines\n{style_str}\n\n"
                    f"## Requirements\n{record['task']}"
                ),
            },
            {
                "role": "assistant",
                "content": record["generated_code"][:8000],  # Cap at 8K chars
            },
        ]
    }


def format_reasoning_example(record: dict) -> dict:
    """Create a reasoning/thinking example that shows the full pipeline logic.
    
    Teaches the model: how to THINK about a coding task step by step,
    considering conventions, architecture, and security.
    """
    # Build the chain-of-thought reasoning
    reasoning_parts = []
    
    reasoning_parts.append(f"Task: {record['task']}")
    reasoning_parts.append(f"Language: {record.get('language', 'python')}")
    reasoning_parts.append(f"Complexity: {record.get('expected_complexity', 'medium')}")
    
    historian = record.get("agent_summaries", {}).get("historian", "")
    if historian:
        reasoning_parts.append(f"\nStep 1 - Convention Analysis:\n{historian}")
    
    architect = record.get("agent_summaries", {}).get("architect", "")
    if architect:
        reasoning_parts.append(f"\nStep 2 - Architecture Mapping:\n{architect}")
    
    planner = record.get("agent_summaries", {}).get("planner", "")
    if planner:
        reasoning_parts.append(f"\nStep 3 - Plan Creation:\n{planner}")
    
    reviewer = record.get("agent_summaries", {}).get("reviewer", "")
    if reviewer:
        reasoning_parts.append(f"\nStep 4 - Review Result:\n{reviewer}")
    
    reasoning_parts.append(f"\nResult: {'SUCCESS' if record.get('success') else 'FAILED'}")
    reasoning_parts.append(f"Attempts: {record.get('attempts', 1)}")
    
    reasoning = "\n".join(reasoning_parts)
    
    return {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a reasoning agent within the MACRO multi-agent pipeline. "
                    "When given a coding task, think step by step: first analyze conventions, "
                    "then map architecture, then create a plan, then assess what the reviewer "
                    "would check. This structured reasoning ensures high-quality, convention-"
                    "compliant code generation."
                ),
            },
            {
                "role": "user",
                "content": f"Think through this coding task step by step:\n\n{record['task']}",
            },
            {
                "role": "assistant",
                "content": reasoning,
            },
        ]
    }


def main():
    parser = argparse.ArgumentParser(
        description="Format MACRO traces into training data"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input JSONL file (raw traces)",
    )
    parser.add_argument(
        "--output", "-o",
        default="data/train.jsonl",
        help="Output JSONL file (training data)",
    )
    parser.add_argument(
        "--min-code-len",
        type=int,
        default=50,
        help="Minimum generated code length to include (default: 50)",
    )
    
    args = parser.parse_args()
    
    # Read input
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"  [X] Input file not found: {args.input}")
        print(f"      Run generate_training_data.py first.")
        sys.exit(1)
    
    records = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    
    print(f"  Loaded {len(records)} raw traces")
    
    # Filter: only successful runs with code
    good_records = [
        r for r in records
        if r.get("success") and len(r.get("generated_code", "")) >= args.min_code_len
    ]
    print(f"  Filtered to {len(good_records)} successful traces (code >= {args.min_code_len} chars)")
    
    # Generate training examples (3 types per record)
    examples = []
    
    for record in good_records:
        # Type 1: Planner training
        planner_ex = format_planner_example(record)
        if planner_ex:
            examples.append(planner_ex)
        
        # Type 2: Implementer training
        impl_ex = format_implementer_example(record)
        if impl_ex:
            examples.append(impl_ex)
        
        # Type 3: Reasoning chain
        reasoning_ex = format_reasoning_example(record)
        if reasoning_ex:
            examples.append(reasoning_ex)
    
    # Also add ALL records (including failed) as reasoning examples
    # Failed runs teach the model what to avoid
    for record in records:
        if not record.get("success") and record.get("agent_summaries"):
            reasoning_ex = format_reasoning_example(record)
            if reasoning_ex:
                examples.append(reasoning_ex)
    
    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    
    print(f"\n  Generated {len(examples)} training examples:")
    print(f"    - Planner examples:    {len(good_records)}")
    print(f"    - Implementer examples: {len(good_records)}")
    print(f"    - Reasoning chains:    {len(examples) - 2 * len(good_records)}")
    print(f"\n  Output: {output_path}")
    print(f"  Next: Upload to GPU and run train.py")


if __name__ == "__main__":
    main()
