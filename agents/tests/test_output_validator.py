"""
Tests for Output Validator — Schema enforcement for agent outputs.
"""

import json
import pytest

from agents.output_validator import (
    validate_agent_output,
    validate_reviewer_verdict,
    try_extract_json,
    build_repair_prompt,
)


# ── Historian Schema Tests ──────────────────────────────────────


class TestHistorianValidation:
    """Validate that Historian output matches the contracted schema."""

    def _valid_historian_output(self) -> dict:
        return {
            "historian_analysis": {
                "metadata": {
                    "confidence_score": 0.7,
                    "prs_analyzed_count": 5,
                },
                "convention_registry": {
                    "naming_conventions": ["snake_case for functions"],
                    "import_conventions": ["stdlib, then third-party, then internal"],
                    "architectural_patterns": ["Repository Pattern"],
                },
                "anti_pattern_registry": ["bare except clauses"],
                "risk_assessment": {
                    "recommendations": ["Add type hints to new code"],
                },
            }
        }

    def test_valid_output_passes(self):
        output = self._valid_historian_output()
        is_valid, errors = validate_agent_output(output, "historian")
        assert is_valid, f"Should pass: {errors}"
        assert errors == []

    def test_missing_metadata_fails(self):
        output = self._valid_historian_output()
        del output["historian_analysis"]["metadata"]
        is_valid, errors = validate_agent_output(output, "historian")
        assert not is_valid
        assert any("metadata" in e for e in errors)

    def test_missing_confidence_score_fails(self):
        output = self._valid_historian_output()
        del output["historian_analysis"]["metadata"]["confidence_score"]
        is_valid, errors = validate_agent_output(output, "historian")
        assert not is_valid
        assert any("confidence_score" in e for e in errors)

    def test_missing_convention_registry_key_fails(self):
        output = self._valid_historian_output()
        del output["historian_analysis"]["convention_registry"]["naming_conventions"]
        is_valid, errors = validate_agent_output(output, "historian")
        assert not is_valid
        assert any("naming_conventions" in e for e in errors)

    def test_missing_anti_pattern_registry_fails(self):
        output = self._valid_historian_output()
        del output["historian_analysis"]["anti_pattern_registry"]
        is_valid, errors = validate_agent_output(output, "historian")
        assert not is_valid
        assert any("anti_pattern_registry" in e for e in errors)

    def test_string_input_parsed_as_json(self):
        output = self._valid_historian_output()
        is_valid, errors = validate_agent_output(json.dumps(output), "historian")
        assert is_valid, f"JSON string should parse: {errors}"

    def test_invalid_json_string_fails(self):
        is_valid, errors = validate_agent_output("not json {{{", "historian")
        assert not is_valid
        assert any("not valid JSON" in e for e in errors)

    def test_non_dict_fails(self):
        is_valid, errors = validate_agent_output([1, 2, 3], "historian")
        assert not is_valid
        assert any("must be a dict" in e for e in errors)

    def test_empty_arrays_still_pass(self):
        """Empty arrays satisfy the schema — no data is valid, not broken."""
        output = {
            "historian_analysis": {
                "metadata": {"confidence_score": 0.1, "prs_analyzed_count": 0},
                "convention_registry": {
                    "naming_conventions": [],
                    "import_conventions": [],
                    "architectural_patterns": [],
                },
                "anti_pattern_registry": [],
                "risk_assessment": {"recommendations": []},
            }
        }
        is_valid, errors = validate_agent_output(output, "historian")
        assert is_valid, f"Empty arrays should pass: {errors}"


# ── Architect Schema Tests ──────────────────────────────────────


class TestArchitectValidation:
    """Validate Architect output with CoAT reasoning."""

    def _valid_architect_output(self) -> dict:
        return {
            "architect_plan": {
                "coat_reasoning": {
                    "files_affected": ["src/api/routes.py"],
                    "historian_conventions_applied": ["snake_case naming"],
                    "risk_factors": ["Low confidence from Historian"],
                    "import_patterns_identified": [],
                    "historian_anti_patterns_avoided": [],
                    "co_evolution_dependencies": [],
                    "precedent_followed": "None",
                    "new_patterns_introduced": [],
                },
                "implementation_steps": [
                    {
                        "step": 1,
                        "action": "Create route handler",
                        "file": "src/api/routes.py",
                        "change_type": "modify",
                        "convention_source": "snake_case from Historian",
                        "details": "Add GET /health endpoint",
                    }
                ],
                "validation_criteria": [
                    "Endpoint returns JSON with status field",
                    "No hardcoded secrets",
                ],
            }
        }

    def test_valid_output_passes(self):
        output = self._valid_architect_output()
        is_valid, errors = validate_agent_output(output, "architect")
        assert is_valid, f"Should pass: {errors}"

    def test_missing_coat_reasoning_fails(self):
        output = self._valid_architect_output()
        del output["architect_plan"]["coat_reasoning"]
        is_valid, errors = validate_agent_output(output, "architect")
        assert not is_valid
        assert any("coat_reasoning" in e for e in errors)

    def test_missing_files_affected_fails(self):
        output = self._valid_architect_output()
        del output["architect_plan"]["coat_reasoning"]["files_affected"]
        is_valid, errors = validate_agent_output(output, "architect")
        assert not is_valid
        assert any("files_affected" in e for e in errors)

    def test_coat_with_empty_cross_refs_still_passes(self):
        """CoAT must exist but can have empty arrays (no history found)."""
        output = self._valid_architect_output()
        output["architect_plan"]["coat_reasoning"]["historian_conventions_applied"] = []
        is_valid, errors = validate_agent_output(output, "architect")
        assert is_valid, f"Empty cross-refs should pass: {errors}"


# ── Reviewer Schema Tests ───────────────────────────────────────


class TestReviewerValidation:
    """Validate Reviewer output and verdict integrity."""

    def _valid_reviewer_output(self, verdict="approved", security_passed=True):
        return {
            "review_result": {
                "verdict": verdict,
                "layer_2_security": {"passed": security_passed},
            }
        }

    def test_approved_passes(self):
        output = self._valid_reviewer_output("approved", True)
        is_valid, errors = validate_agent_output(output, "reviewer")
        assert is_valid, f"Should pass: {errors}"

    def test_changes_requested_passes(self):
        output = self._valid_reviewer_output("changes_requested", False)
        is_valid, errors = validate_agent_output(output, "reviewer")
        assert is_valid, f"Should pass: {errors}"

    def test_invalid_verdict_fails(self):
        output = self._valid_reviewer_output("maybe", True)
        is_valid, errors = validate_agent_output(output, "reviewer")
        assert not is_valid
        assert any("Invalid verdict" in e for e in errors)

    def test_missing_verdict_fails(self):
        output = {"review_result": {"layer_2_security": {"passed": True}}}
        is_valid, errors = validate_agent_output(output, "reviewer")
        assert not is_valid
        assert any("verdict" in e for e in errors)


class TestVerdictIntegrity:
    """The verdict cross-check: security fail → MUST reject."""

    def test_security_fail_with_approved_is_violation(self):
        output = {
            "review_result": {
                "verdict": "approved",
                "layer_2_security": {"passed": False},
            }
        }
        ok, msg = validate_reviewer_verdict(output)
        assert not ok
        assert "INTEGRITY VIOLATION" in msg

    def test_security_fail_with_reject_is_ok(self):
        output = {
            "review_result": {
                "verdict": "changes_requested",
                "layer_2_security": {"passed": False},
            }
        }
        ok, msg = validate_reviewer_verdict(output)
        assert ok
        assert msg == "OK"

    def test_security_pass_with_approved_is_ok(self):
        output = {
            "review_result": {
                "verdict": "approved",
                "layer_2_security": {"passed": True},
            }
        }
        ok, msg = validate_reviewer_verdict(output)
        assert ok

    def test_missing_review_result_fails(self):
        ok, msg = validate_reviewer_verdict({})
        assert not ok
        assert "Missing key" in msg


# ── JSON Extraction Tests ───────────────────────────────────────


class TestJsonExtraction:
    """LLMs wrap JSON in markdown — we need to handle it."""

    def test_raw_json(self):
        raw = '{"key": "value"}'
        result = try_extract_json(raw)
        assert result == {"key": "value"}

    def test_json_in_code_block(self):
        raw = 'Here is my output:\n```json\n{"key": "value"}\n```\nDone.'
        result = try_extract_json(raw)
        assert result == {"key": "value"}

    def test_json_in_generic_code_block(self):
        raw = '```\n{"key": "value"}\n```'
        result = try_extract_json(raw)
        assert result == {"key": "value"}

    def test_json_with_prose(self):
        raw = 'The output is:\n\n{"key": "value"}\n\nAs shown above.'
        result = try_extract_json(raw)
        assert result == {"key": "value"}

    def test_no_json_returns_none(self):
        raw = "This is just text with no JSON at all."
        result = try_extract_json(raw)
        assert result is None

    def test_complex_nested_json(self):
        data = {"historian_analysis": {"metadata": {"score": 0.8}}}
        raw = f"```json\n{json.dumps(data, indent=2)}\n```"
        result = try_extract_json(raw)
        assert result == data


# ── Repair Prompt Tests ─────────────────────────────────────────


class TestRepairPrompt:
    """Ensure repair prompts include the error context."""

    def test_includes_errors(self):
        prompt = build_repair_prompt(
            "historian", '{"broken": true}', ["Missing required key: metadata"]
        )
        assert "historian" in prompt
        assert "Missing required key: metadata" in prompt
        assert '{"broken": true}' in prompt

    def test_truncates_long_output(self):
        long_output = "x" * 5000
        prompt = build_repair_prompt("architect", long_output, ["Error"])
        # Should truncate to 2000 chars
        assert len(prompt) < 5000


# ── Unknown Agent Type Tests ────────────────────────────────────


class TestUnknownAgent:
    """Unknown agent types should pass (no schema to validate)."""

    def test_unknown_agent_passes(self):
        is_valid, errors = validate_agent_output({"any": "data"}, "implementer")
        assert is_valid
        assert errors == []

    def test_unknown_agent_with_string_passes(self):
        is_valid, errors = validate_agent_output('{"any": "data"}', "unknown")
        assert is_valid
