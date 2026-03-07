"""
Output Validator — Post-LLM Contract Enforcement

Ensures agents produce the JSON schema defined in their system prompts
before passing output to downstream agents.

Used by the Orchestrator as a validation gate between pipeline stages.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

# ── Schema Definitions ──────────────────────────────────────────

HISTORIAN_REQUIRED_KEYS: Dict[str, Any] = {
    "historian_analysis": {
        "metadata": ["confidence_score", "prs_analyzed_count"],
        "convention_registry": [
            "naming_conventions",
            "import_conventions",
            "architectural_patterns",
        ],
        "anti_pattern_registry": None,  # must exist (any type)
        "risk_assessment": ["recommendations"],
    }
}

ARCHITECT_REQUIRED_KEYS: Dict[str, Any] = {
    "architect_plan": {
        "coat_reasoning": [
            "files_affected",
            "historian_conventions_applied",
            "risk_factors",
        ],
        "implementation_steps": None,
        "validation_criteria": None,
    }
}

REVIEWER_REQUIRED_KEYS: Dict[str, Any] = {
    "review_result": {
        "verdict": None,  # "approved" or "changes_requested"
        "layer_2_security": ["passed"],
    }
}

VALID_VERDICTS = {"approved", "changes_requested"}


# ── Core Validator ──────────────────────────────────────────────

def validate_agent_output(
    output: Any,
    agent_type: str,
) -> Tuple[bool, List[str]]:
    """
    Validate that an agent's LLM output conforms to its contract.

    Args:
        output: dict or JSON string from the agent
        agent_type: "historian" | "architect" | "reviewer"

    Returns:
        (is_valid, list_of_error_messages)
    """
    errors: List[str] = []

    # Parse if string
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError as e:
            return False, [f"Output is not valid JSON: {e}"]

    if not isinstance(output, dict):
        return False, [f"Output must be a dict, got {type(output).__name__}"]

    schema_map = {
        "historian": HISTORIAN_REQUIRED_KEYS,
        "architect": ARCHITECT_REQUIRED_KEYS,
        "reviewer": REVIEWER_REQUIRED_KEYS,
    }

    schema = schema_map.get(agent_type)
    if schema is None:
        return True, []  # no schema defined → pass

    errors = _check_keys(output, schema, path="")

    # Reviewer-specific: validate verdict value
    if agent_type == "reviewer" and not errors:
        verdict = output.get("review_result", {}).get("verdict")
        if verdict and verdict not in VALID_VERDICTS:
            errors.append(
                f"Invalid verdict '{verdict}'. Must be one of: {VALID_VERDICTS}"
            )

    return len(errors) == 0, errors


def _check_keys(
    data: Dict[str, Any],
    schema: Dict[str, Any],
    path: str,
) -> List[str]:
    """Recursively check that required keys exist."""
    errors: List[str] = []

    for key, subschema in schema.items():
        full_path = f"{path}.{key}" if path else key

        if key not in data:
            errors.append(f"Missing required key: {full_path}")
            continue

        if isinstance(subschema, dict):
            # Nested object — recurse
            if not isinstance(data[key], dict):
                errors.append(
                    f"{full_path} should be a dict, got {type(data[key]).__name__}"
                )
            else:
                errors.extend(_check_keys(data[key], subschema, full_path))

        elif isinstance(subschema, list):
            # subschema is a list of required sub-keys
            if isinstance(data[key], dict):
                for subkey in subschema:
                    if subkey not in data[key]:
                        errors.append(
                            f"Missing required key: {full_path}.{subkey}"
                        )
            # If it's a list/other type, the key exists — OK

    return errors


# ── Verdict Integrity Check ─────────────────────────────────────

def validate_reviewer_verdict(output: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Enforce deterministic verdict logic.

    Security failures MUST result in "changes_requested".
    If the Reviewer says "approved" but security layer failed,
    that's an integrity violation — override to reject.

    Args:
        output: The reviewer's output dict

    Returns:
        (is_valid, message)
    """
    try:
        result = output["review_result"]
        verdict = result["verdict"]
        security_passed = result.get("layer_2_security", {}).get("passed", True)

        if not security_passed and verdict == "approved":
            return False, (
                "INTEGRITY VIOLATION: Reviewer approved code with security failures. "
                "Verdict overridden to 'changes_requested'."
            )

        return True, "OK"

    except (KeyError, TypeError) as e:
        return False, f"Missing key in review output: {e}"


# ── Heuristic Output Parser ────────────────────────────────────

def try_extract_json(raw_output: str) -> Optional[Dict[str, Any]]:
    """
    Attempt to extract JSON from messy LLM output.

    LLMs sometimes wrap JSON in markdown code blocks or
    add prose before/after. This function handles common cases:
    1. Raw JSON string
    2. JSON inside ```json ... ``` blocks
    3. JSON inside ``` ... ``` blocks
    """
    raw_output = raw_output.strip()

    # Case 1: Direct JSON
    if raw_output.startswith("{"):
        try:
            return json.loads(raw_output)
        except json.JSONDecodeError:
            pass

    # Case 2: Inside ```json ... ``` or ``` ... ``` blocks
    import re
    json_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw_output, re.DOTALL)
    if json_block:
        try:
            return json.loads(json_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Case 3: Find first { ... } block (greedy)
    brace_start = raw_output.find("{")
    brace_end = raw_output.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(raw_output[brace_start : brace_end + 1])
        except json.JSONDecodeError:
            pass

    return None


# ── Repair Prompt ───────────────────────────────────────────────

def build_repair_prompt(
    agent_type: str,
    raw_output: str,
    errors: List[str],
) -> str:
    """
    Build a follow-up prompt asking the LLM to fix its JSON output.

    Used by the orchestrator when schema validation fails.
    """
    return (
        f"Your previous output for the {agent_type} agent failed schema validation.\n\n"
        f"Errors:\n" + "\n".join(f"- {e}" for e in errors) + "\n\n"
        f"Your raw output was:\n```\n{raw_output[:2000]}\n```\n\n"
        f"Please output ONLY valid JSON that satisfies the schema. "
        f"No prose, no markdown fences — just the JSON object."
    )
