"""
GitHub Resolver — Clone remote repos for MACRO to analyze.

Handles:
- Clone to cached dir (~/.contextual-architect/repos/)
- Auto-detect programming language from file extensions
- Validate GitHub slug format
- Support private repos via GITHUB_TOKEN
"""

import subprocess
from collections import Counter
from pathlib import Path
from typing import Optional, Tuple

# Language detection by file extension
_EXTENSION_MAP = {
    ".py": "python",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".java": "java",
}

# Extensions to ignore during language detection
_IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "vendor", "dist", "build", ".tox", ".mypy_cache",
}


def detect_language(repo_path: str) -> str:
    """Auto-detect the dominant programming language in a repository.

    Scans file extensions and returns the language with the most files.
    Falls back to 'python' if detection fails.
    """
    counts: Counter = Counter()
    root = Path(repo_path)

    try:
        for path in root.rglob("*"):
            # Skip ignored directories
            if any(part in _IGNORE_DIRS for part in path.parts):
                continue
            if path.is_file() and path.suffix in _EXTENSION_MAP:
                counts[_EXTENSION_MAP[path.suffix]] += 1
    except (OSError, PermissionError):
        pass

    if not counts:
        return "python"  # Safe default

    return counts.most_common(1)[0][0]


def resolve_github_repo(
    github_slug: str,
    token: Optional[str] = None,
    branch: Optional[str] = None,
) -> Tuple[str, str]:
    """Clone a GitHub repo and return (local_path, detected_language).

    Args:
        github_slug: "owner/repo" format (e.g., "tiangolo/fastapi")
        token: GitHub personal access token (for private repos)
        branch: Specific branch to clone (default: repo's default branch)

    Returns:
        Tuple of (local_path, detected_language)

    Raises:
        ValueError: If slug format is invalid
        RuntimeError: If clone fails
    """
    # Validate slug format
    parts = github_slug.strip().split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Invalid GitHub slug: '{github_slug}'. "
            f"Use 'owner/repo' format (e.g., 'tiangolo/fastapi')."
        )

    owner, repo = parts[0], parts[1]

    # Remove .git suffix if present
    if repo.endswith(".git"):
        repo = repo[:-4]

    # Determine cache path
    cache_dir = Path.home() / ".contextual-architect" / "repos"
    cache_path = cache_dir / owner / repo

    # If already cached, pull latest
    if cache_path.exists() and (cache_path / ".git").exists():
        try:
            subprocess.run(
                ["git", "pull", "--ff-only", "--quiet"],
                cwd=str(cache_path),
                capture_output=True,
                timeout=60,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # Pull failure is non-fatal — use stale cache
        local_path = str(cache_path)
    else:
        # Clone fresh — shallow clone for speed
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        if token:
            clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
        else:
            clone_url = f"https://github.com/{owner}/{repo}.git"

        cmd = ["git", "clone", "--depth", "50", "--quiet"]
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([clone_url, str(cache_path)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            # Clean error message — don't leak token
            error_msg = result.stderr.replace(token, "***") if token else result.stderr
            raise RuntimeError(
                f"Failed to clone '{github_slug}': {error_msg.strip()}"
            )

        local_path = str(cache_path)

    # Auto-detect language
    language = detect_language(local_path)

    return local_path, language


def clear_cache(github_slug: Optional[str] = None) -> int:
    """Remove cached repos. Returns number of repos removed."""
    import shutil

    cache_dir = Path.home() / ".contextual-architect" / "repos"

    if not cache_dir.exists():
        return 0

    if github_slug:
        parts = github_slug.split("/")
        if len(parts) == 2:
            target = cache_dir / parts[0] / parts[1]
            if target.exists():
                shutil.rmtree(target)
                return 1
        return 0

    # Clear all
    count = 0
    for owner_dir in cache_dir.iterdir():
        if owner_dir.is_dir():
            for repo_dir in owner_dir.iterdir():
                if repo_dir.is_dir():
                    shutil.rmtree(repo_dir)
                    count += 1
    return count
