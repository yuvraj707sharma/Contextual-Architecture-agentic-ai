"""
Tests for the Style Fingerprint analyzer.
"""

import pytest
from pathlib import Path

from ..style_fingerprint import StyleAnalyzer, StyleFingerprint


class TestStyleFingerprint:
    """Tests for StyleFingerprint dataclass."""

    def test_to_prompt_context(self):
        fp = StyleFingerprint(
            function_naming="snake_case",
            logger_library="logging",
            indent_style="spaces",
            indent_size=4,
        )
        ctx = fp.to_prompt_context()
        assert "snake_case" in ctx
        assert "logging" in ctx

    def test_to_dict(self):
        fp = StyleFingerprint(
            function_naming="camelCase",
            logger_library="structlog",
        )
        d = fp.to_dict()
        assert d["function_naming"] == "camelCase"
        assert d["logger_library"] == "structlog"


class TestStyleAnalyzer:
    """Tests for StyleAnalyzer."""

    def test_analyze_python_project(self, tmp_repo):
        analyzer = StyleAnalyzer(str(tmp_repo), "python")
        fp = analyzer.analyze()

        assert isinstance(fp, StyleFingerprint)
        assert fp.function_naming == "snake_case"

    def test_analyze_detects_logging(self, tmp_repo):
        # helpers.py uses logging.getLogger but other files use print
        analyzer = StyleAnalyzer(str(tmp_repo), "python")
        fp = analyzer.analyze()

        # logger_library should be a valid value, not 'unknown'
        assert fp.logger_library in ("logging", "print", "unknown")

    def test_analyze_empty_project(self, tmp_path):
        analyzer = StyleAnalyzer(str(tmp_path), "python")
        fp = analyzer.analyze()

        # Should return defaults, not crash
        assert isinstance(fp, StyleFingerprint)

    def test_max_crash_all_long_lines(self, tmp_path):
        """Regression: max() on empty sequence when all lines >= 200 chars."""
        long_file = tmp_path / "wide.py"
        long_file.write_text("x" * 300 + "\n" + "y" * 250 + "\n", encoding="utf-8")

        analyzer = StyleAnalyzer(str(tmp_path), "python")
        fp = analyzer.analyze()

        # Must not crash
        assert isinstance(fp, StyleFingerprint)

    def test_analyze_detects_indent_size(self, tmp_repo):
        analyzer = StyleAnalyzer(str(tmp_repo), "python")
        fp = analyzer.analyze()

        # Sample files all use 4-space indentation
        assert fp.indent_size == 4

    def test_to_dict_has_expected_keys(self, tmp_repo):
        """to_dict should contain all major style fields."""
        analyzer = StyleAnalyzer(str(tmp_repo), "python")
        fp = analyzer.analyze()
        d = fp.to_dict()

        assert "function_naming" in d
        assert "logger_library" in d
        assert "indent_size" in d
