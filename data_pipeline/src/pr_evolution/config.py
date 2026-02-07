"""
Configuration for the PR Evolution Extractor.

This module defines quality filters and target repositories
for extracting "production-grade" training data.

UPDATED: Addressed code review feedback:
1. Made CORRECTION_PATTERNS more specific (multi-word phrases only)
2. Added minimum comment length filter
3. Added quality scoring system
4. Added training data security filters
"""

from dataclasses import dataclass, field
from typing import List
import re


@dataclass
class ExtractionConfig:
    """Configuration for PR extraction quality gates."""
    
    # Minimum number of review comments to consider a PR "valuable"
    min_review_comments: int = 2
    
    # Only PRs that were merged (not closed without merge)
    merged_only: bool = True
    
    # Minimum lines changed (ignore tiny PRs)
    min_lines_changed: int = 10
    
    # Maximum lines changed (ignore massive PRs - too noisy)
    max_lines_changed: int = 1000
    
    # QUALITY FILTER: Minimum comment length (characters)
    # Short comments like "LGTM" or "test this" are noise
    min_comment_length: int = 50
    
    # QUALITY FILTER: Minimum quality score (0-100)
    # Calculated based on pattern matches, code suggestions, etc.
    min_quality_score: int = 40
    
    # Languages to focus on
    target_languages: List[str] = field(default_factory=lambda: [
        "go", "python", "typescript", "javascript", "rust"
    ])
    
    # File extensions to include
    file_extensions: List[str] = field(default_factory=lambda: [
        ".go", ".py", ".ts", ".js", ".tsx", ".jsx", ".rs"
    ])
    
    # Exclude test files from training (optional - can be toggled)
    exclude_tests: bool = False
    
    # Exclude vendor/node_modules/etc
    exclude_patterns: List[str] = field(default_factory=lambda: [
        "vendor/", "node_modules/", "dist/", "build/", ".min.", "__pycache__"
    ])


@dataclass
class RepoConfig:
    """Configuration for a target repository."""
    
    owner: str
    repo: str
    
    # Language of the primary codebase
    language: str = "go"
    
    # Maximum PRs to extract
    max_prs: int = 100
    
    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


# "Gold Standard" repositories - high quality, well-maintained, good PR culture
GOLD_STANDARD_REPOS = [
    # Go repositories
    RepoConfig("gofiber", "fiber", "go"),
    RepoConfig("gin-gonic", "gin", "go"),
    RepoConfig("go-gitea", "gitea", "go"),
    RepoConfig("prometheus", "prometheus", "go"),
    
    # Python repositories
    RepoConfig("fastapi", "fastapi", "python"),
    RepoConfig("pydantic", "pydantic", "python"),
    RepoConfig("pallets", "flask", "python"),
    RepoConfig("encode", "httpx", "python"),
    
    # TypeScript repositories
    RepoConfig("microsoft", "vscode", "typescript"),
    RepoConfig("vercel", "next.js", "typescript"),
    RepoConfig("trpc", "trpc", "typescript"),
    RepoConfig("prisma", "prisma", "typescript"),
]


# ============================================================================
# UPDATED: More specific patterns (multi-word phrases to avoid false positives)
# ============================================================================

# These patterns indicate ARCHITECTURAL feedback (high-value training data)
CORRECTION_PATTERNS_STRONG = [
    # Style/Pattern corrections (explicit phrases)
    "instead of using", "you should use", "prefer using", "better to use",
    "don't use this", "avoid using", "we don't use", "we prefer",
    "our convention is", "the pattern here is", "we usually do",
    "this should be", "please change to", "can you refactor",
    
    # Error handling (specific phrases)
    "handle the error", "missing error handling", "error should be",
    "wrap the error", "don't ignore the error", "check the error",
    "return the error", "propagate the error",
    
    # Security concerns (specific phrases)
    "security issue", "security vulnerability", "sql injection",
    "xss vulnerability", "csrf token", "sanitize the input",
    "validate the input", "escape the", "never trust",
    
    # Performance (specific phrases)
    "performance issue", "memory leak", "allocates too much",
    "use a buffer", "avoid allocation", "goroutine leak",
    "mutex contention", "race condition",
    
    # Architecture (specific phrases)
    "extract this to", "move this to", "should be in its own",
    "violates single responsibility", "tight coupling",
    "dependency injection", "interface segregation",
    "this belongs in", "separate concern",
]

# Weaker patterns - only count if combined with other signals
CORRECTION_PATTERNS_WEAK = [
    "refactor", "cleanup", "simplify", "extract", "separate",
    "internal/", "pkg/", "layer", "module", "package",
]

# Patterns that indicate a GitHub "suggestion" block (high-quality signal)
SUGGESTION_PATTERN = re.compile(r'```suggestion\s*\n(.+?)\n```', re.DOTALL)

# Patterns that indicate code in the comment (medium-quality signal)
CODE_BLOCK_PATTERN = re.compile(r'```\w*\n(.+?)\n```', re.DOTALL)


# ============================================================================
# SECURITY: Training Data Audit Patterns
# ============================================================================

# Patterns that might indicate leaked secrets (EXCLUDE these from training)
SECRET_PATTERNS = [
    re.compile(r'AKIA[0-9A-Z]{16}'),  # AWS Access Key
    re.compile(r'ghp_[a-zA-Z0-9]{36}'),  # GitHub Personal Access Token
    re.compile(r'sk-[a-zA-Z0-9]{48}'),  # OpenAI API Key
    re.compile(r'-----BEGIN (RSA |EC )?PRIVATE KEY-----'),  # Private keys
    re.compile(r'password\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),  # Hardcoded passwords
    re.compile(r'api[_-]?key\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),  # API keys
    re.compile(r'secret\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),  # Secrets
]

# Known CVE-affected patterns (warn but don't exclude - these are learning opportunities)
VULNERABLE_PATTERNS = [
    ("log4j", "CVE-2021-44228"),
    ("struts", "CVE-2017-5638"),
    ("eval(", "code injection risk"),
    ("exec(", "code injection risk"),
    ("shell=True", "command injection risk"),
]


def calculate_quality_score(comment_body: str, has_code_suggestion: bool = False) -> int:
    """
    Calculate a quality score (0-100) for a review comment.
    
    High scores indicate comments that teach "architectural lessons" -
    exactly what we want for training data.
    
    Scoring:
    - Strong pattern match: +20 per match (max 60)
    - Weak pattern match: +5 per match (max 15)
    - Has GitHub suggestion block: +25
    - Has code block: +10
    - Comment length > 100 chars: +10
    - Comment length > 200 chars: +10
    """
    score = 0
    comment_lower = comment_body.lower()
    
    # Strong patterns (high value)
    strong_matches = sum(1 for p in CORRECTION_PATTERNS_STRONG if p.lower() in comment_lower)
    score += min(strong_matches * 20, 60)
    
    # Weak patterns (lower value, capped)
    weak_matches = sum(1 for p in CORRECTION_PATTERNS_WEAK if p.lower() in comment_lower)
    score += min(weak_matches * 5, 15)
    
    # GitHub suggestion block (very high value - actual code fix)
    if SUGGESTION_PATTERN.search(comment_body):
        score += 25
    elif CODE_BLOCK_PATTERN.search(comment_body):
        score += 10
    
    # Length bonus (longer comments = more context)
    if len(comment_body) > 100:
        score += 10
    if len(comment_body) > 200:
        score += 10
    
    return min(score, 100)


def check_for_secrets(code: str) -> List[str]:
    """
    Check if code contains potential secrets.
    Returns list of warning messages if secrets found.
    """
    warnings = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(code):
            warnings.append(f"Potential secret detected: {pattern.pattern[:30]}...")
    return warnings


def check_for_vulnerabilities(code: str) -> List[tuple]:
    """
    Check if code contains known vulnerable patterns.
    Returns list of (pattern, cve_or_risk) tuples.
    """
    found = []
    code_lower = code.lower()
    for pattern, cve in VULNERABLE_PATTERNS:
        if pattern.lower() in code_lower:
            found.append((pattern, cve))
    return found
