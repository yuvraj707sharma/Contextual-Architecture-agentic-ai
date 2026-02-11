"""
Tests for data_pipeline.src.pr_evolution.config module.

Tests configuration classes, quality scoring, and security checks.
"""

import pytest
from src.pr_evolution.config import (
    ExtractionConfig,
    RepoConfig,
    calculate_quality_score,
    check_for_secrets,
    check_for_vulnerabilities,
    CORRECTION_PATTERNS_STRONG,
)


class TestExtractionConfig:
    """Tests for ExtractionConfig dataclass."""
    
    def test_default_values(self):
        """Test that default values are set correctly."""
        config = ExtractionConfig()
        
        assert config.min_review_comments == 2
        assert config.merged_only is True
        assert config.min_lines_changed == 10
        assert config.max_lines_changed == 1000
        assert config.min_comment_length == 50
        assert config.min_quality_score == 40
        assert "go" in config.target_languages
        assert "python" in config.target_languages
        assert ".go" in config.file_extensions
        assert ".py" in config.file_extensions
    
    def test_custom_values(self):
        """Test creating config with custom values."""
        config = ExtractionConfig(
            min_review_comments=5,
            min_quality_score=60,
            target_languages=["go"],
        )
        
        assert config.min_review_comments == 5
        assert config.min_quality_score == 60
        assert config.target_languages == ["go"]


class TestRepoConfig:
    """Tests for RepoConfig dataclass."""
    
    def test_full_name_property(self):
        """Test full_name property combines owner and repo."""
        config = RepoConfig(owner="golang", repo="go")
        
        assert config.full_name == "golang/go"
    
    def test_full_name_with_hyphen(self):
        """Test full_name with hyphenated names."""
        config = RepoConfig(owner="microsoft", repo="vscode-go")
        
        assert config.full_name == "microsoft/vscode-go"
    
    def test_default_language(self):
        """Test default language is 'go'."""
        config = RepoConfig(owner="test", repo="repo")
        
        assert config.language == "go"
    
    def test_custom_language(self):
        """Test setting custom language."""
        config = RepoConfig(owner="python", repo="cpython", language="python")
        
        assert config.language == "python"


class TestCalculateQualityScore:
    """Tests for calculate_quality_score function."""
    
    def test_low_quality_score(self):
        """Test comment with low quality gets low score."""
        comment = "LGTM"
        
        score = calculate_quality_score(comment)
        
        assert score < 40  # Below minimum threshold
    
    def test_medium_quality_score(self):
        """Test comment with medium quality indicators."""
        comment = "Please refactor this code to use our standard pattern. The current approach is okay but we usually prefer a different style. Instead of using the old method, you should use the new one."
        
        score = calculate_quality_score(comment)
        
        assert 40 <= score < 80
    
    def test_high_quality_score_with_strong_patterns(self):
        """Test comment with strong correction patterns."""
        comment = """Instead of using log.Println, you should use our logger with context. 
        Also, please handle the error properly by wrapping it with context. 
        This is a security issue because we never trust raw user input."""
        
        score = calculate_quality_score(comment)
        
        assert score >= 60  # Multiple strong patterns
    
    def test_suggestion_block_bonus(self):
        """Test that GitHub suggestion blocks add significant score."""
        comment = """Please change to:
```suggestion
func validate(s string) error {
    return fmt.Errorf("invalid: %s", s)
}
```"""
        
        score = calculate_quality_score(comment)
        
        # Should get +25 for suggestion block
        assert score >= 25
    
    def test_code_block_bonus(self):
        """Test that code blocks (non-suggestion) add moderate score."""
        comment = """Try this approach:
```go
func example() {
    // code here
}
```"""
        
        score = calculate_quality_score(comment)
        
        # Should get +10 for code block
        assert score >= 10
    
    def test_length_bonus(self):
        """Test that longer comments get bonus points."""
        short_comment = "a" * 50  # Just meets minimum
        medium_comment = "a" * 150  # Over 100
        long_comment = "a" * 250  # Over 200
        
        short_score = calculate_quality_score(short_comment)
        medium_score = calculate_quality_score(medium_comment)
        long_score = calculate_quality_score(long_comment)
        
        # Longer comments should score higher (other things equal)
        assert medium_score > short_score
        assert long_score > medium_score
    
    def test_score_capped_at_100(self):
        """Test that score never exceeds 100."""
        # Create comment with many strong patterns
        comment = " ".join(CORRECTION_PATTERNS_STRONG) * 10
        comment += "\n```suggestion\ncode here\n```"
        
        score = calculate_quality_score(comment)
        
        assert score <= 100
    
    def test_empty_comment(self):
        """Test empty comment gets zero score."""
        score = calculate_quality_score("")
        
        assert score == 0


class TestCheckForSecrets:
    """Tests for check_for_secrets function."""
    
    def test_aws_access_key_detected(self):
        """Test detection of AWS access keys."""
        code = 'aws_key = "AKIAIOSFODNN7EXAMPLE"'
        
        warnings = check_for_secrets(code)
        
        assert len(warnings) > 0
        assert any("secret" in w.lower() for w in warnings)
    
    def test_github_token_detected(self):
        """Test detection of GitHub personal access tokens."""
        code = 'token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"'
        
        warnings = check_for_secrets(code)
        
        assert len(warnings) > 0
    
    def test_openai_api_key_detected(self):
        """Test detection of OpenAI API keys."""
        code = 'api_key = "sk-1234567890abcdefghijklmnopqrstuvwxyz12345678"'
        
        warnings = check_for_secrets(code)
        
        assert len(warnings) > 0
    
    def test_hardcoded_password_detected(self):
        """Test detection of hardcoded passwords."""
        code = 'password = "mySecretP@ssw0rd"'
        
        warnings = check_for_secrets(code)
        
        assert len(warnings) > 0
    
    def test_api_key_assignment_detected(self):
        """Test detection of API key assignments."""
        code = 'api_key = "1234567890abcdef"'
        
        warnings = check_for_secrets(code)
        
        assert len(warnings) > 0
    
    def test_private_key_detected(self):
        """Test detection of private keys."""
        code = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA...
-----END RSA PRIVATE KEY-----"""
        
        warnings = check_for_secrets(code)
        
        assert len(warnings) > 0
    
    def test_clean_code_no_warnings(self):
        """Test that clean code produces no warnings."""
        code = """
func processData(input string) error {
    result := validate(input)
    return result
}
"""
        
        warnings = check_for_secrets(code)
        
        assert len(warnings) == 0
    
    def test_environment_variable_usage_safe(self):
        """Test that environment variable usage is safe (not flagged)."""
        code = 'api_key = os.getenv("API_KEY")'
        
        warnings = check_for_secrets(code)
        
        # Should not flag env var usage (no hardcoded value)
        assert len(warnings) == 0


class TestCheckForVulnerabilities:
    """Tests for check_for_vulnerabilities function."""
    
    def test_log4j_pattern(self):
        """Test detection of log4j usage."""
        code = "import org.apache.logging.log4j"
        
        vulns = check_for_vulnerabilities(code)
        
        assert len(vulns) > 0
        assert any("log4j" in str(v) for v in vulns)
    
    def test_eval_detected(self):
        """Test detection of eval() usage."""
        code = 'result = eval(user_input)'
        
        vulns = check_for_vulnerabilities(code)
        
        assert len(vulns) > 0
        assert any("injection" in str(v).lower() for v in vulns)
    
    def test_exec_detected(self):
        """Test detection of exec() usage."""
        code = 'exec(user_code)'
        
        vulns = check_for_vulnerabilities(code)
        
        assert len(vulns) > 0
    
    def test_shell_true_detected(self):
        """Test detection of shell=True in subprocess."""
        code = 'subprocess.call(cmd, shell=True)'
        
        vulns = check_for_vulnerabilities(code)
        
        assert len(vulns) > 0
        assert any("injection" in str(v).lower() for v in vulns)
    
    def test_clean_code_no_vulnerabilities(self):
        """Test that safe code produces no vulnerability warnings."""
        code = """
def safe_function(data):
    validated = sanitize(data)
    return process(validated)
"""
        
        vulns = check_for_vulnerabilities(code)
        
        assert len(vulns) == 0


class TestCorrectionPatternsStrong:
    """Tests for CORRECTION_PATTERNS_STRONG validation."""
    
    def test_all_patterns_are_multi_word(self):
        """Verify all strong patterns are multi-word phrases.
        
        This is critical to avoid false positives. Single-word patterns
        would match too broadly.
        """
        for pattern in CORRECTION_PATTERNS_STRONG:
            assert " " in pattern, f"Pattern '{pattern}' should be multi-word"
    
    def test_patterns_are_specific(self):
        """Verify patterns are specific enough to be meaningful."""
        for pattern in CORRECTION_PATTERNS_STRONG:
            # Multi-word means at least 2 words (space separated)
            words = pattern.split()
            assert len(words) >= 2, f"Pattern '{pattern}' not specific enough"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
