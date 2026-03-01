"""
Convert conversation logs (markdown) into training data for MACRO distillation.

Parses human/assistant conversation transcripts and extracts:
- Bug diagnosis + fix pairs
- Feature request + implementation pairs
- Architecture decision + reasoning pairs
- Code review + patch pairs

Usage:
    python conversation_to_dataset.py --input conversations/ --output data/conversation_train.jsonl
    python conversation_to_dataset.py --input my_chat.md --output data/conversation_train.jsonl
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional


# Minimum lengths to filter out trivial exchanges
MIN_USER_LEN = 20      # "yes", "ok", "continue" get filtered
MIN_ASSISTANT_LEN = 100  # Short acknowledgments get filtered
MIN_CODE_LEN = 30       # Code blocks must be substantial


def parse_conversation(text: str) -> List[Dict[str, str]]:
    """Parse a markdown conversation into turns.
    
    Supports formats:
    - "Human: ... Ai: ... Ai thinking: ..."
    - "### User Input ... ### Planner Response ..."
    - "User: ... Assistant: ..."
    - "**User**: ... **Assistant**: ..."
    """
    turns = []
    
    # Split text into lines for sequential parsing
    lines = text.split("\n")
    current_role = None
    current_content = []
    
    # Role markers (checked in order of priority)
    user_markers = [
        "Human:", "Human :", "User:", "USER:",
        "### User Input", "### Human",
    ]
    assistant_markers = [
        "Ai thinking:", "Ai :", "Ai:",
        "AI:", "Assistant:", "ASSISTANT:",
        "### Planner Response", "### Assistant", "### AI",
    ]
    
    def flush():
        """Save accumulated content as a turn."""
        nonlocal current_role, current_content
        if current_role and current_content:
            content = "\n".join(current_content).strip()
            if content:
                turns.append({"role": current_role, "content": content})
        current_content = []
    
    for line in lines:
        stripped = line.strip()
        
        # Check for user markers
        matched = False
        for marker in user_markers:
            if stripped.startswith(marker) or stripped == marker.rstrip(":"):
                flush()
                current_role = "user"
                # Content after the marker on the same line
                after = stripped[len(marker):].strip()
                current_content = [after] if after else []
                matched = True
                break
        
        if matched:
            continue
        
        # Check for assistant markers
        for marker in assistant_markers:
            if stripped.startswith(marker) or stripped == marker.rstrip(":"):
                flush()
                current_role = "assistant"
                after = stripped[len(marker):].strip()
                current_content = [after] if after else []
                matched = True
                break
        
        if matched:
            continue
        
        # Regular line — append to current turn
        if current_role:
            current_content.append(line)
    
    # Flush last turn
    flush()
    
    # Merge consecutive same-role turns (e.g., Ai thinking + Ai response)
    merged = []
    for turn in turns:
        if merged and merged[-1]["role"] == turn["role"]:
            merged[-1]["content"] += "\n\n" + turn["content"]
        else:
            merged.append(turn)
    
    return merged


def extract_code_blocks(text: str) -> List[str]:
    """Extract code blocks from markdown text."""
    pattern = r'```(?:\w+)?\n(.*?)```'
    blocks = re.findall(pattern, text, re.DOTALL)
    return [b.strip() for b in blocks if len(b.strip()) >= MIN_CODE_LEN]


def classify_exchange(user_msg: str, assistant_msg: str) -> Optional[str]:
    """Classify the type of exchange for training.
    
    Returns: 'bug_fix', 'feature', 'architecture', 'review', 'reasoning', or None
    """
    user_lower = user_msg.lower()
    assistant_lower = assistant_msg.lower()
    
    # Bug fix: user reports a problem, assistant diagnoses and fixes
    bug_keywords = ["error", "bug", "crash", "fail", "broke", "broken", "fix", "issue", "wrong", "doesn't work"]
    if any(k in user_lower for k in bug_keywords) and extract_code_blocks(assistant_msg):
        return "bug_fix"
    
    # Feature request: user asks for something new
    feature_keywords = ["add", "create", "build", "implement", "make", "write", "generate"]
    if any(k in user_lower for k in feature_keywords) and extract_code_blocks(assistant_msg):
        return "feature"
    
    # Architecture: user asks about design decisions
    arch_keywords = ["should i", "how should", "which approach", "architecture", "design", "pattern", "trade-off"]
    if any(k in user_lower for k in arch_keywords):
        return "architecture"
    
    # Code review: assistant identifies issues in code
    review_keywords = ["review", "check", "audit", "vulnerability", "security", "improve"]
    if any(k in user_lower for k in review_keywords) or any(k in assistant_lower for k in review_keywords):
        return "review"
    
    # General reasoning with substance
    if len(assistant_msg) > 300 and (extract_code_blocks(assistant_msg) or "|" in assistant_msg):
        return "reasoning"
    
    return None


def turn_pair_to_training(
    user_msg: str,
    assistant_msg: str,
    exchange_type: str,
    source_file: str = "",
) -> Optional[Dict]:
    """Convert a user-assistant pair into a training example."""
    
    # System prompts based on exchange type
    system_prompts = {
        "bug_fix": (
            "You are an expert debugging agent within the MACRO pipeline. "
            "When a user reports a bug, you diagnose the root cause, explain "
            "the fix, and provide corrected code that follows the project's conventions."
        ),
        "feature": (
            "You are a code implementation agent within the MACRO pipeline. "
            "When a user requests a feature, you plan the implementation, "
            "consider the project's architecture and conventions, and produce "
            "production-grade code with proper error handling."
        ),
        "architecture": (
            "You are an architecture reasoning agent within the MACRO pipeline. "
            "When asked about design decisions, you analyze trade-offs, consider "
            "the project's constraints, and provide clear recommendations with "
            "justification."
        ),
        "review": (
            "You are a code review agent within the MACRO pipeline. "
            "You identify bugs, security vulnerabilities (CWE denylist), "
            "performance issues, and convention violations. You provide "
            "specific fixes with corrected code."
        ),
        "reasoning": (
            "You are a reasoning agent within the MACRO multi-agent pipeline. "
            "You think through problems step by step, considering conventions, "
            "architecture, security, and the project's specific patterns."
        ),
    }
    
    system = system_prompts.get(exchange_type, system_prompts["reasoning"])
    
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg[:4000]},
            {"role": "assistant", "content": assistant_msg[:8000]},
        ],
        "metadata": {
            "type": exchange_type,
            "source": source_file,
            "user_len": len(user_msg),
            "assistant_len": len(assistant_msg),
            "has_code": bool(extract_code_blocks(assistant_msg)),
        }
    }


def process_file(filepath: Path) -> List[Dict]:
    """Process a single conversation file into training examples."""
    text = filepath.read_text(encoding="utf-8", errors="ignore")
    turns = parse_conversation(text)
    
    examples = []
    
    # Process consecutive user-assistant pairs
    i = 0
    while i < len(turns) - 1:
        if turns[i]["role"] == "user" and turns[i + 1]["role"] == "assistant":
            user_msg = turns[i]["content"]
            assistant_msg = turns[i + 1]["content"]
            
            # Filter trivial exchanges
            if len(user_msg) < MIN_USER_LEN or len(assistant_msg) < MIN_ASSISTANT_LEN:
                i += 1
                continue
            
            # Classify and convert
            exchange_type = classify_exchange(user_msg, assistant_msg)
            if exchange_type:
                example = turn_pair_to_training(
                    user_msg, assistant_msg, exchange_type,
                    source_file=filepath.name,
                )
                if example:
                    examples.append(example)
            
            i += 2
        else:
            i += 1
    
    return examples


def main():
    parser = argparse.ArgumentParser(
        description="Convert conversation logs into training data"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input file or directory of conversation .md/.txt files",
    )
    parser.add_argument(
        "--output", "-o",
        default="data/conversation_train.jsonl",
        help="Output JSONL file",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing output file instead of overwriting",
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    
    # Collect files
    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        files = list(input_path.glob("**/*.md")) + list(input_path.glob("**/*.txt"))
    else:
        print(f"  [X] Input not found: {args.input}")
        sys.exit(1)
    
    print(f"  Found {len(files)} conversation file(s)")
    
    # Process all files
    all_examples = []
    for filepath in files:
        examples = process_file(filepath)
        if examples:
            print(f"    {filepath.name}: {len(examples)} examples")
            all_examples.extend(examples)
    
    if not all_examples:
        print("  [!] No training examples extracted.")
        print("      Make sure your conversation files have clear user/assistant markers.")
        sys.exit(1)
    
    # Count types
    type_counts = {}
    for ex in all_examples:
        t = ex["metadata"]["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    
    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    mode = "a" if args.append else "w"
    with open(output_path, mode, encoding="utf-8") as f:
        for ex in all_examples:
            # Remove metadata before writing (not needed for training)
            training_ex = {"messages": ex["messages"]}
            f.write(json.dumps(training_ex) + "\n")
    
    print(f"\n  Extracted {len(all_examples)} training examples:")
    for t, count in sorted(type_counts.items()):
        print(f"    {t}: {count}")
    print(f"\n  Output: {output_path}")


if __name__ == "__main__":
    main()
