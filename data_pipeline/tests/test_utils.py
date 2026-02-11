"""
Tests for data_pipeline.src.utils module.

Tests language detection and comment categorization utilities.
"""

import pytest
from src.utils import (
    detect_language_from_path,
    detect_language_from_code,
    categorize_comment,
    EXTENSION_TO_LANGUAGE,
    CORRECTION_PATTERNS_STRONG,
)


class TestDetectLanguageFromPath:
    """Tests for detect_language_from_path function."""
    
    def test_go_extension(self):
        assert detect_language_from_path("main.go") == "go"
        assert detect_language_from_path("src/handlers/user.go") == "go"
    
    def test_python_extension(self):
        assert detect_language_from_path("app.py") == "python"
        assert detect_language_from_path("src/utils/helpers.py") == "python"
    
    def test_typescript_extensions(self):
        assert detect_language_from_path("app.ts") == "typescript"
        assert detect_language_from_path("Component.tsx") == "typescript"
    
    def test_javascript_extensions(self):
        assert detect_language_from_path("app.js") == "javascript"
        assert detect_language_from_path("Component.jsx") == "javascript"
    
    def test_rust_extension(self):
        assert detect_language_from_path("main.rs") == "rust"
    
    def test_java_extension(self):
        assert detect_language_from_path("Main.java") == "java"
    
    def test_ruby_extension(self):
        assert detect_language_from_path("app.rb") == "ruby"
    
    def test_php_extension(self):
        assert detect_language_from_path("index.php") == "php"
    
    def test_c_extensions(self):
        assert detect_language_from_path("main.c") == "c"
        assert detect_language_from_path("header.h") == "c"
    
    def test_cpp_extensions(self):
        assert detect_language_from_path("main.cpp") == "cpp"
        assert detect_language_from_path("header.hpp") == "cpp"
    
    def test_none_path(self):
        assert detect_language_from_path(None) is None
    
    def test_unknown_extension(self):
        assert detect_language_from_path("file.unknown") is None
        assert detect_language_from_path("README.md") is None
    
    def test_no_extension(self):
        assert detect_language_from_path("Makefile") is None


class TestDetectLanguageFromCode:
    """Tests for detect_language_from_code function."""
    
    def test_go_package_declaration(self):
        code = "package main\n\nfunc main() {}"
        assert detect_language_from_code(code) == "go"
    
    def test_python_def_keyword(self):
        code = "def hello_world():\n    print('hello')"
        assert detect_language_from_code(code) == "python"
    
    def test_rust_fn_with_double_colon(self):
        code = "fn main() {\n    std::io::println!(\"hello\");\n}"
        assert detect_language_from_code(code) == "rust"
    
    def test_typescript_type_annotations(self):
        code = "function greet(name: string): void {\n    console.log(name);\n}"
        assert detect_language_from_code(code) == "typescript"
    
    def test_javascript_arrow_function(self):
        code = "const add = (a, b) => a + b;"
        assert detect_language_from_code(code) == "javascript"
    
    def test_empty_code(self):
        assert detect_language_from_code("") == "unknown"
        assert detect_language_from_code("   ") == "unknown"
    
    def test_file_path_priority_over_heuristics(self):
        # Even if code looks like Python, file extension takes priority
        python_code = "def hello():\n    pass"
        assert detect_language_from_code(python_code, "test.go") == "go"
        assert detect_language_from_code(python_code, "test.js") == "javascript"
    
    def test_python_import_heuristic(self):
        code = "import os\nfrom pathlib import Path\n\nif __name__ == '__main__':\n    pass"
        assert detect_language_from_code(code) == "python"
    
    def test_go_func_defer_heuristic(self):
        code = "func cleanup() {\n    defer file.Close()\n    x := 5\n}"
        assert detect_language_from_code(code) == "go"


class TestCategorizeComment:
    """Tests for categorize_comment function."""
    
    def test_security_category(self):
        comment = "This has a security vulnerability - SQL injection risk"
        assert categorize_comment(comment) == "security"
        
        comment = "Need to sanitize the input to prevent XSS"
        assert categorize_comment(comment) == "security"
        
        comment = "Never trust user input directly"
        assert categorize_comment(comment) == "security"
    
    def test_error_handling_category(self):
        comment = "You need to handle the error here"
        assert categorize_comment(comment) == "error_handling"
        
        comment = "Missing error handling - should check the error"
        assert categorize_comment(comment) == "error_handling"
        
        comment = "Don't ignore the error, wrap the error with context"
        assert categorize_comment(comment) == "error_handling"
    
    def test_testing_category(self):
        comment = "Please add a test case for this"
        assert categorize_comment(comment) == "testing"
        
        comment = "Missing test coverage for error paths"
        assert categorize_comment(comment) == "testing"
        
        comment = "Need better assertions in the unit test"
        assert categorize_comment(comment) == "testing"
    
    def test_performance_category(self):
        comment = "This allocates too much memory - performance issue"
        assert categorize_comment(comment) == "performance"
        
        comment = "Potential memory leak in goroutine"
        assert categorize_comment(comment) == "performance"
        
        comment = "Use a buffer to optimize this"
        assert categorize_comment(comment) == "performance"
    
    def test_architecture_category(self):
        comment = "Extract this to a separate interface"
        assert categorize_comment(comment) == "architecture"
        
        comment = "This violates single responsibility principle"
        assert categorize_comment(comment) == "architecture"
        
        comment = "Improve coupling between modules"
        assert categorize_comment(comment) == "architecture"
    
    def test_style_category(self):
        comment = "Our convention is to use camelCase for variables"
        assert categorize_comment(comment) == "style"
        
        comment = "This doesn't match our naming convention"
        assert categorize_comment(comment) == "style"
        
        comment = "Please format according to style guide"
        assert categorize_comment(comment) == "style"
    
    def test_project_structure_category(self):
        comment = "This should move to the internal/ directory"
        assert categorize_comment(comment) == "project_structure"
        
        comment = "This belongs in the pkg/ package"
        assert categorize_comment(comment) == "project_structure"
    
    def test_general_category(self):
        comment = "Looks good to me!"
        assert categorize_comment(comment) == "general"
        
        comment = "Nice work on this change"
        assert categorize_comment(comment) == "general"


class TestCorrectionPatternsStrong:
    """Tests for CORRECTION_PATTERNS_STRONG validation."""
    
    def test_all_patterns_are_multi_word(self):
        """Verify all patterns are multi-word phrases to avoid false positives."""
        for pattern in CORRECTION_PATTERNS_STRONG:
            # Each pattern should have at least one space (multi-word)
            assert " " in pattern, f"Pattern '{pattern}' is not multi-word"
    
    def test_patterns_are_lowercase(self):
        """Patterns should be lowercase for case-insensitive matching."""
        for pattern in CORRECTION_PATTERNS_STRONG:
            assert pattern == pattern.lower(), f"Pattern '{pattern}' is not lowercase"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
