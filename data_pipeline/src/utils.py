"""
Shared utilities for data pipeline modules.

Contains common functions used by both pr_evolution and codereviewer modules.
"""

import re
from typing import List, Optional


# =============================================================================
# LANGUAGE DETECTION
# =============================================================================

# File extension to language mapping (primary source of truth)
EXTENSION_TO_LANGUAGE = {
    ".go": "go",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
}


def detect_language_from_path(file_path: Optional[str]) -> Optional[str]:
    """
    Detect language from file path extension.
    This is the most reliable method.
    """
    if not file_path:
        return None
    
    for ext, lang in EXTENSION_TO_LANGUAGE.items():
        if file_path.endswith(ext):
            return lang
    return None


def detect_language_from_code(code: str, file_path: Optional[str] = None) -> str:
    """
    Detect programming language from code content.
    
    Priority:
    1. File extension (most reliable)
    2. Strong language-specific patterns
    3. Weak heuristics (fallback)
    
    Args:
        code: The code content
        file_path: Optional file path for extension-based detection
        
    Returns:
        Language string or "unknown"
    """
    # Priority 1: Use file extension if available
    if file_path:
        lang = detect_language_from_path(file_path)
        if lang:
            return lang
    
    # Priority 2: Strong language-specific patterns
    # These are patterns unique to specific languages
    
    # Go: package declaration is required in every Go file
    if re.search(r'^package\s+\w+', code, re.MULTILINE):
        return "go"
    
    # Rust: fn main() or use/mod statements with ::
    if re.search(r'\bfn\s+\w+\s*\(', code) and '::' in code:
        return "rust"
    
    # Python: def with no type annotations common, or __init__, or # type: comments
    if re.search(r'^\s*def\s+\w+\s*\([^)]*\)\s*:', code, re.MULTILINE):
        # Check it's not Ruby (Ruby uses def but different syntax)
        if 'end' not in code.split('\n')[-10:]:  # Ruby ends blocks with 'end'
            return "python"
    
    # TypeScript: explicit type annotations with :
    if re.search(r':\s*(string|number|boolean|void|any)\s*[;=)]', code):
        return "typescript"
    
    # JavaScript: const/let with arrow functions, no type annotations
    if re.search(r'\bconst\s+\w+\s*=\s*\([^)]*\)\s*=>', code):
        return "javascript"
    
    # Priority 3: Weaker heuristics
    code_lower = code.lower()
    
    # Python imports
    if 'import ' in code and ('from ' in code or '__name__' in code):
        return "python"
    
    # Go-specific keywords
    if 'func ' in code and (':=' in code or 'defer ' in code):
        return "go"
    
    return "unknown"


# =============================================================================
# LESSON CATEGORIZATION
# =============================================================================

# Strong patterns indicate architectural feedback (high-value training data)
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


def categorize_comment(comment: str) -> str:
    """
    Categorize a review comment into a lesson type.
    
    This classifies the type of feedback being given,
    which helps during training to teach the model
    different types of corrections.
    
    Categories:
    - security: Security vulnerabilities and fixes
    - error_handling: Error handling patterns
    - testing: Test coverage, mocking, assertions
    - performance: Performance optimizations
    - architecture: Design patterns, modularity
    - style: Naming, formatting conventions
    - project_structure: Directory layout, package organization
    - general: Other feedback
    """
    comment_lower = comment.lower()
    
    # Priority order matters - check most specific first
    
    # Security
    if any(p in comment_lower for p in [
        "security", "vulnerability", "injection", "xss", "csrf",
        "sanitize", "validate input", "escape", "never trust"
    ]):
        return "security"
    
    # Error handling
    if any(p in comment_lower for p in [
        "handle the error", "missing error", "error handling",
        "check the error", "return the error", "wrap the error",
        "panic", "recover", "exception"
    ]):
        return "error_handling"
    
    # Testing
    if any(p in comment_lower for p in [
        "test coverage", "add a test", "unit test", "missing test",
        "mock", "assertion", "test case"
    ]):
        return "testing"
    
    # Performance
    if any(p in comment_lower for p in [
        "performance", "memory leak", "allocat", "goroutine",
        "async", "mutex", "race condition", "buffer", "optimize"
    ]):
        return "performance"
    
    # Architecture
    if any(p in comment_lower for p in [
        "interface", "abstract", "dependency injection", "coupling",
        "single responsibility", "extract this", "refactor",
        "design pattern", "solid"
    ]):
        return "architecture"
    
    # Style
    if any(p in comment_lower for p in [
        "convention", "naming", "format", "style guide",
        "we usually", "consistent with"
    ]):
        return "style"
    
    # Project structure
    if any(p in comment_lower for p in [
        "internal/", "pkg/", "move this to", "belongs in",
        "package", "directory", "module"
    ]):
        return "project_structure"
    
    return "general"
