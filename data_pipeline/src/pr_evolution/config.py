"""
Configuration for the PR Evolution Extractor.

This module defines quality filters and target repositories
for extracting "production-grade" training data.
"""

from dataclasses import dataclass, field
from typing import List


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


# Review comment patterns that indicate "correction logic"
# These are the comments that teach the model what NOT to do
CORRECTION_PATTERNS = [
    # Style/Pattern corrections
    "instead of", "should be", "prefer", "better to", "don't use",
    "we usually", "our convention", "the pattern here is",
    
    # Error handling
    "handle the error", "missing error", "error handling", "wrap the error",
    
    # Security concerns  
    "security", "vulnerability", "injection", "sanitize", "validate",
    
    # Performance
    "performance", "allocate", "memory", "goroutine", "mutex",
    
    # Architecture
    "interface", "dependency", "coupling", "module", "separate",
    "internal/", "pkg/", "layer",
    
    # Testing
    "test", "coverage", "mock", "assert",
]
