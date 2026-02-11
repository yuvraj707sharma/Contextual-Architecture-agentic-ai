"""
Tests for data_pipeline.src.codereviewer.downloader module.

Tests dataset conversion and language detection utilities.
"""

import pytest
from src.codereviewer.downloader import (
    convert_refinement_sample,
    get_language_from_sample,
)


class TestConvertRefinementSample:
    """Tests for convert_refinement_sample function."""
    
    def test_valid_sample_conversion(self):
        """Test conversion of a valid CodeReviewer sample."""
        sample = {
            "old_code": "def hello():\n    print('hi')",
            "new_code": "def hello():\n    print('hello')",
            "comment": "Please use more descriptive output",
            "lang": "python",
            "path": "src/main.py",
        }
        
        result = convert_refinement_sample(sample)
        
        assert result is not None
        assert result["original_code"] == "def hello():\n    print('hi')"
        assert result["fixed_code"] == "def hello():\n    print('hello')"
        assert result["reviewer_comment"] == "Please use more descriptive output"
        assert result["language"] == "python"
        assert result["file_path"] == "src/main.py"
        assert result["repo"] == "codereviewer_dataset"
        assert result["source"] == "microsoft_codereviewer"
    
    def test_alternative_field_names(self):
        """Test conversion with alternative field names (old/new vs old_code/new_code)."""
        sample = {
            "old": "x = 1",
            "new": "x = 2",
            "msg": "Update value",
            "language": "python",
        }
        
        result = convert_refinement_sample(sample)
        
        assert result is not None
        assert result["original_code"] == "x = 1"
        assert result["fixed_code"] == "x = 2"
        assert result["reviewer_comment"] == "Update value"
    
    def test_missing_old_code_returns_none(self):
        """Test that sample without old code returns None."""
        sample = {
            "new_code": "fixed code",
            "comment": "comment",
        }
        
        result = convert_refinement_sample(sample)
        
        assert result is None
    
    def test_missing_new_code_returns_none(self):
        """Test that sample without new code returns None."""
        sample = {
            "old_code": "original code",
            "comment": "comment",
        }
        
        result = convert_refinement_sample(sample)
        
        assert result is None
    
    def test_empty_code_returns_none(self):
        """Test that sample with empty code returns None."""
        sample = {
            "old_code": "   ",
            "new_code": "   ",
            "comment": "comment",
        }
        
        result = convert_refinement_sample(sample)
        
        assert result is None
    
    def test_go_language_sample(self):
        """Test conversion of Go language sample."""
        sample = {
            "old_code": "func main() {\n\tlog.Println(err)\n}",
            "new_code": "func main() {\n\tfmt.Errorf(\"%w\", err)\n}",
            "comment": "Handle the error properly",
            "lang": "go",
        }
        
        result = convert_refinement_sample(sample)
        
        assert result is not None
        assert result["language"] == "go"
    
    def test_javascript_sample(self):
        """Test conversion of JavaScript sample."""
        sample = {
            "old_code": "const x = function() {}",
            "new_code": "const x = () => {}",
            "comment": "Use arrow function",
            "lang": "javascript",
        }
        
        result = convert_refinement_sample(sample)
        
        assert result is not None
        assert result["language"] == "javascript"
    
    def test_typescript_sample(self):
        """Test conversion of TypeScript sample."""
        sample = {
            "old_code": "function greet(name) { return name; }",
            "new_code": "function greet(name: string): string { return name; }",
            "comment": "Add type annotations",
            "lang": "typescript",
        }
        
        result = convert_refinement_sample(sample)
        
        assert result is not None
        assert result["language"] == "typescript"
    
    def test_unknown_language_excluded(self):
        """Test that samples with unknown languages are excluded."""
        sample = {
            "old_code": "some code",
            "new_code": "fixed code",
            "comment": "fix it",
            "lang": "cobol",  # Not in TARGET_LANGUAGES
        }
        
        result = convert_refinement_sample(sample)
        
        # Unknown languages not in target list should be excluded
        assert result is None
    
    def test_unknown_language_from_detection_included(self):
        """Test that unknown language from detection is included if detected."""
        sample = {
            "old_code": "def hello():\n    pass",
            "new_code": "def hello():\n    print('hi')",
            "comment": "Add output",
            # No lang field - will be detected from code
        }
        
        result = convert_refinement_sample(sample)
        
        # Should detect Python and include it
        assert result is not None
        assert result["language"] == "python"
    
    def test_lesson_category_assigned(self):
        """Test that lesson category is assigned based on comment."""
        sample = {
            "old_code": "password = 'admin'",
            "new_code": "password = os.getenv('PASSWORD')",
            "comment": "Never trust hardcoded passwords - security vulnerability",
            "lang": "python",
        }
        
        result = convert_refinement_sample(sample)
        
        assert result is not None
        assert result["lesson_category"] == "security"
    
    def test_quality_score_default(self):
        """Test that default quality score is assigned."""
        sample = {
            "old_code": "x = 1",
            "new_code": "x = 2",
            "comment": "update",
            "lang": "python",
        }
        
        result = convert_refinement_sample(sample)
        
        assert result is not None
        assert result["quality_score"] == 50  # Base score for dataset
    
    def test_metadata_preserved(self):
        """Test that original metadata is preserved."""
        sample = {
            "old_code": "code1",
            "new_code": "code2",
            "comment": "fix",
            "lang": "python",
            "extra_field": "extra_value",
            "pr_id": 123,
        }
        
        result = convert_refinement_sample(sample)
        
        assert result is not None
        assert "metadata" in result
        assert "original_sample" in result["metadata"]
        # Check that extra fields are in metadata (but not old/new code)
        assert "extra_field" in result["metadata"]["original_sample"]
        assert "pr_id" in result["metadata"]["original_sample"]


class TestGetLanguageFromSample:
    """Tests for get_language_from_sample function."""
    
    def test_explicit_lang_field(self):
        """Test that explicit 'lang' field is used first."""
        sample = {"lang": "python"}
        code = "package main"  # Looks like Go
        
        result = get_language_from_sample(sample, code)
        
        assert result == "python"  # Explicit field takes priority
    
    def test_explicit_language_field(self):
        """Test that explicit 'language' field works."""
        sample = {"language": "JavaScript"}
        code = "def test(): pass"  # Looks like Python
        
        result = get_language_from_sample(sample, code)
        
        assert result == "javascript"  # Lowercased
    
    def test_file_path_fallback(self):
        """Test that file path is used when no explicit language."""
        sample = {"path": "src/main.go"}
        code = "some code"
        
        result = get_language_from_sample(sample, code)
        
        assert result == "go"
    
    def test_filename_field_fallback(self):
        """Test alternative 'filename' field."""
        sample = {"filename": "app.py"}
        code = "code here"
        
        result = get_language_from_sample(sample, code)
        
        assert result == "python"
    
    def test_code_heuristic_fallback(self):
        """Test that code heuristics are used as last resort."""
        sample = {}  # No language or path
        code = "package main\n\nfunc main() {}"
        
        result = get_language_from_sample(sample, code)
        
        assert result == "go"
    
    def test_typescript_detection_from_code(self):
        """Test TypeScript detection from code content."""
        sample = {}
        code = "function greet(name: string): void {}"
        
        result = get_language_from_sample(sample, code)
        
        assert result == "typescript"
    
    def test_unknown_when_no_detection(self):
        """Test unknown language when nothing matches."""
        sample = {}
        code = "unknown syntax here"
        
        result = get_language_from_sample(sample, code)
        
        assert result == "unknown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
