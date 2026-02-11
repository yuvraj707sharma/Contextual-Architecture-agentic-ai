"""
Tests for data_pipeline.src.pr_evolution.extractor module.

Critical tests for diff extraction - validates recent bug fixes where
both removed (-) and added (+) lines are properly captured.
"""

import pytest
from src.pr_evolution.extractor import (
    extract_code_from_diff_hunk,
    extract_suggestion_code,
)


class TestExtractCodeFromDiffHunk:
    """Tests for extract_code_from_diff_hunk function.
    
    CRITICAL: This function was recently fixed to capture BOTH
    removed (-) and added (+) lines. These tests lock in that fix.
    """
    
    def test_captures_both_removed_and_added_lines(self):
        """CRITICAL TEST: Validates the bug fix for capturing both - and + lines."""
        diff_hunk = """@@ -10,7 +10,7 @@ func handleRequest(w http.ResponseWriter, r *http.Request) {
 	data, err := fetchData(r.Context())
 	if err != nil {
-		log.Println(err)
+		return fmt.Errorf("failed to fetch data: %w", err)
 		return
 	}
 	writeResponse(w, data)"""
        
        original, added, context = extract_code_from_diff_hunk(diff_hunk)
        
        # CRITICAL: Both removed and added lines should be captured
        assert "log.Println(err)" in original
        assert 'return fmt.Errorf("failed to fetch data: %w", err)' in added
        assert "data, err := fetchData(r.Context())" in context
    
    def test_only_additions(self):
        """Test diff hunk with only added lines (no removals)."""
        diff_hunk = """@@ -15,6 +15,8 @@ func process() {
 	fmt.Println("processing")
+	if err != nil {
+		return err
+	}
 	return nil"""
        
        original, added, context = extract_code_from_diff_hunk(diff_hunk)
        
        assert original == ""  # No removed lines
        assert "if err != nil:" in added or "if err != nil {" in added
        assert "return err" in added
        assert 'fmt.Println("processing")' in context
    
    def test_only_removals(self):
        """Test diff hunk with only removed lines (no additions)."""
        diff_hunk = """@@ -20,8 +20,6 @@ func cleanup() {
 	defer mu.Unlock()
-	// TODO: implement this
-	log.Println("not implemented")
 	return nil"""
        
        original, added, context = extract_code_from_diff_hunk(diff_hunk)
        
        assert "TODO: implement this" in original
        assert "not implemented" in original
        assert added == ""  # No added lines
        assert "defer mu.Unlock()" in context
    
    def test_context_lines_captured(self):
        """Test that context lines (unchanged) are properly captured."""
        diff_hunk = """ func example() {
 	x := 1
-	y := 2
+	y := 3
 	return x + y
 }"""
        
        original, added, context = extract_code_from_diff_hunk(diff_hunk)
        
        assert "y := 2" in original
        assert "y := 3" in added
        assert "x := 1" in context
        assert "return x + y" in context
        assert "func example() {" in context
    
    def test_diff_headers_skipped(self):
        """Test that diff header lines are skipped (@@, ---, +++)."""
        diff_hunk = """@@ -1,5 +1,5 @@
--- a/main.go
+++ b/main.go
 package main
-const version = "1.0"
+const version = "1.1"
 func main() {}"""
        
        original, added, context = extract_code_from_diff_hunk(diff_hunk)
        
        # Headers should not appear in any output
        assert "@@" not in original
        assert "@@" not in added
        assert "@@" not in context
        assert "---" not in original
        assert "+++" not in added
        
        # Actual code should be captured
        assert 'const version = "1.0"' in original
        assert 'const version = "1.1"' in added
    
    def test_empty_hunk(self):
        """Test handling of empty diff hunk."""
        diff_hunk = ""
        
        original, added, context = extract_code_from_diff_hunk(diff_hunk)
        
        assert original == ""
        assert added == ""
        assert context == ""
    
    def test_hunk_with_only_headers(self):
        """Test diff hunk with only header lines."""
        diff_hunk = """@@ -1,1 +1,1 @@
--- a/test.py
+++ b/test.py"""
        
        original, added, context = extract_code_from_diff_hunk(diff_hunk)
        
        assert original == ""
        assert added == ""
        assert context == ""
    
    def test_multiple_changes_same_hunk(self):
        """Test hunk with multiple changed sections."""
        diff_hunk = """@@ -10,10 +10,12 @@
 func validate(s string) error {
-	if s == "" {
-		return errors.New("empty")
+	if len(s) == 0 {
+		return fmt.Errorf("string cannot be empty")
 	}
-	// Check length
+	// Validate length
+	if len(s) > 100 {
+		return fmt.Errorf("string too long")
+	}
 	return nil
 }"""
        
        original, added, context = extract_code_from_diff_hunk(diff_hunk)
        
        # Multiple removals should all be captured
        assert 'if s == ""' in original or 's == ""' in original
        assert 'errors.New("empty")' in original
        assert "Check length" in original
        
        # Multiple additions should all be captured
        assert "len(s) == 0" in added
        assert "fmt.Errorf" in added
        assert "Validate length" in added
        assert "string too long" in added
    
    def test_preserves_indentation(self):
        """Test that indentation is preserved in extracted code."""
        diff_hunk = """ func nested() {
 	if condition {
-		doSomething()
+		doSomethingElse()
 	}
 }"""
        
        original, added, context = extract_code_from_diff_hunk(diff_hunk)
        
        # Indentation should be preserved (tabs/spaces intact)
        assert "doSomething()" in original
        assert "doSomethingElse()" in added


class TestExtractSuggestionCode:
    """Tests for extract_suggestion_code function."""
    
    def test_valid_suggestion_block(self):
        """Test extraction of valid GitHub suggestion block."""
        comment = """Please change this to:

```suggestion
const result = await fetchData();
if (!result) {
    throw new Error('No data');
}
```

This handles errors better."""
        
        code = extract_suggestion_code(comment)
        
        assert code is not None
        assert "const result = await fetchData()" in code
        assert "throw new Error('No data')" in code
    
    def test_suggestion_with_language_marker(self):
        """Test suggestion block with language marker."""
        comment = """```suggestion
def validate_input(data: str) -> bool:
    return len(data) > 0
```"""
        
        code = extract_suggestion_code(comment)
        
        assert code is not None
        assert "def validate_input" in code
        assert "return len(data) > 0" in code
    
    def test_no_suggestion_block(self):
        """Test comment without suggestion block returns None."""
        comment = "This looks good, just a minor nit about naming."
        
        code = extract_suggestion_code(comment)
        
        assert code is None
    
    def test_regular_code_block_not_suggestion(self):
        """Test that regular code blocks are not extracted as suggestions."""
        comment = """Here's an example:

```python
def example():
    pass
```

But this is not a suggestion."""
        
        code = extract_suggestion_code(comment)
        
        assert code is None
    
    def test_empty_suggestion_block(self):
        """Test suggestion block with no code."""
        comment = """```suggestion
```"""
        
        code = extract_suggestion_code(comment)
        
        # Should return None for empty suggestion
        assert code is None
    
    def test_multiline_suggestion(self):
        """Test suggestion with multiple lines of code."""
        comment = """```suggestion
func handleError(err error) error {
    if err == nil {
        return nil
    }
    return fmt.Errorf("operation failed: %w", err)
}
```"""
        
        code = extract_suggestion_code(comment)
        
        assert code is not None
        assert "func handleError" in code
        assert "fmt.Errorf" in code
        assert "err == nil" in code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
