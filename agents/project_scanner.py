"""
Project Scanner - Deep environment and dependency analysis.

Runs FIRST in the pipeline, before all other agents.
Produces a ProjectSnapshot that gives every downstream agent
full awareness of the project environment:

- File tree (respects .gitignore)
- Dependencies with versions
- Framework detection (React, Flask, Django, etc.)
- Auth system detection (Firebase, Supabase, etc.)
- Database detection (PostgreSQL, MongoDB, etc.)
- Environment analysis (.env keys, Docker, CI/CD)
- Entry points and build system
"""

import os
import re
import time
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

from .logger import get_logger


# ── Directories / files to always skip ────────────────────

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".contextual-architect", ".next", ".nuxt", "dist", "build",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "coverage",
    ".tox", ".eggs", "*.egg-info", "target", "vendor",
}

SKIP_FILES = {
    ".DS_Store", "Thumbs.db", "desktop.ini",
}


# ── Detection rules ──────────────────────────────────────

FRAMEWORK_SIGNATURES = {
    # JavaScript / TypeScript
    "react": {"imports": ["react", "react-dom"], "deps": ["react"]},
    "next.js": {"imports": ["next"], "deps": ["next"]},
    "vue": {"imports": ["vue"], "deps": ["vue"]},
    "nuxt": {"imports": ["nuxt"], "deps": ["nuxt"]},
    "angular": {"imports": ["@angular/core"], "deps": ["@angular/core"]},
    "svelte": {"imports": ["svelte"], "deps": ["svelte"]},
    "express": {"imports": ["express"], "deps": ["express"]},
    "fastify": {"imports": ["fastify"], "deps": ["fastify"]},
    "nest.js": {"imports": ["@nestjs/core"], "deps": ["@nestjs/core"]},
    # Python
    "flask": {"imports": ["flask"], "deps": ["flask", "Flask"]},
    "django": {"imports": ["django"], "deps": ["django", "Django"]},
    "fastapi": {"imports": ["fastapi"], "deps": ["fastapi"]},
    "streamlit": {"imports": ["streamlit"], "deps": ["streamlit"]},
    "pygame": {"imports": ["pygame"], "deps": ["pygame"]},
    "pytorch": {"imports": ["torch"], "deps": ["torch"]},
    "tensorflow": {"imports": ["tensorflow"], "deps": ["tensorflow"]},
    # Go
    "gin": {"imports": ["github.com/gin-gonic/gin"], "deps": ["gin"]},
    "fiber": {"imports": ["github.com/gofiber/fiber"], "deps": ["fiber"]},
    "echo": {"imports": ["github.com/labstack/echo"], "deps": ["echo"]},
}

AUTH_SIGNATURES = {
    "firebase": {"imports": ["firebase", "firebase-admin", "firebase_admin"], "files": ["firebase.json", "firebaseConfig"]},
    "supabase": {"imports": ["supabase", "@supabase/supabase-js"], "files": ["supabase"]},
    "auth0": {"imports": ["auth0", "@auth0/nextjs-auth0", "auth0-python"], "files": ["auth0"]},
    "clerk": {"imports": ["@clerk/nextjs", "@clerk/clerk-react"], "files": ["clerk"]},
    "passport": {"imports": ["passport"], "files": []},
    "jwt": {"imports": ["jsonwebtoken", "pyjwt", "PyJWT", "jose"], "files": []},
    "oauth": {"imports": ["oauthlib", "oauth2client", "passport-oauth"], "files": []},
    "nextauth": {"imports": ["next-auth"], "files": ["[...nextauth]"]},
}

DB_SIGNATURES = {
    "postgresql": {"imports": ["psycopg2", "asyncpg", "pg"], "deps": ["psycopg2", "asyncpg", "pg"]},
    "mongodb": {"imports": ["pymongo", "mongoose", "mongodb"], "deps": ["pymongo", "mongoose", "mongodb"]},
    "sqlite": {"imports": ["sqlite3", "better-sqlite3"], "deps": ["sqlite3"]},
    "mysql": {"imports": ["mysql", "mysql2", "pymysql"], "deps": ["mysql2", "pymysql"]},
    "prisma": {"imports": ["@prisma/client"], "files": ["prisma/schema.prisma"]},
    "sqlalchemy": {"imports": ["sqlalchemy"], "deps": ["sqlalchemy", "SQLAlchemy"]},
    "typeorm": {"imports": ["typeorm"], "deps": ["typeorm"]},
    "drizzle": {"imports": ["drizzle-orm"], "deps": ["drizzle-orm"]},
    "redis": {"imports": ["redis", "ioredis"], "deps": ["redis", "ioredis"]},
}


# ── Data Classes ─────────────────────────────────────────

@dataclass
class FileEntry:
    """A file in the project tree."""
    path: str           # relative path
    size_bytes: int
    language: str = ""
    
    def to_dict(self):
        return {"path": self.path, "size": self.size_bytes, "lang": self.language}


@dataclass
class ProjectSnapshot:
    """Complete environment snapshot of a project."""
    
    # Structure
    total_files: int = 0
    total_dirs: int = 0
    file_tree: List[FileEntry] = field(default_factory=list)
    dir_tree: List[str] = field(default_factory=list)
    
    # Dependencies
    dependencies: Dict[str, str] = field(default_factory=dict)  # name -> version
    dev_dependencies: Dict[str, str] = field(default_factory=dict)
    
    # Detected technology stack
    language: str = ""
    frameworks: List[str] = field(default_factory=list)
    auth_systems: List[str] = field(default_factory=list)
    databases: List[str] = field(default_factory=list)
    
    # Environment
    env_keys: List[str] = field(default_factory=list)  # names only, never values
    has_docker: bool = False
    has_ci: bool = False
    ci_platform: str = ""  # "github_actions", "gitlab_ci", etc.
    
    # Build system
    package_manager: str = ""  # npm, yarn, pnpm, pip, poetry, uv
    build_tool: str = ""       # webpack, vite, esbuild, setuptools
    test_runner: str = ""      # pytest, jest, vitest, go test
    
    # Entry points
    entry_points: List[str] = field(default_factory=list)
    
    # Config files found
    config_files: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files": self.total_files,
            "total_dirs": self.total_dirs,
            "language": self.language,
            "frameworks": self.frameworks,
            "auth_systems": self.auth_systems,
            "databases": self.databases,
            "dependencies": self.dependencies,
            "dev_dependencies": self.dev_dependencies,
            "env_keys": self.env_keys,
            "has_docker": self.has_docker,
            "has_ci": self.has_ci,
            "ci_platform": self.ci_platform,
            "package_manager": self.package_manager,
            "build_tool": self.build_tool,
            "test_runner": self.test_runner,
            "entry_points": self.entry_points,
            "config_files": self.config_files,
            "dir_tree": self.dir_tree[:30],  # Cap for prompt size
            "files_sample": [f.to_dict() for f in self.file_tree[:50]],
        }
    
    def to_prompt_context(self, detailed: bool = False) -> str:
        """Convert to a prompt string for LLM agents.
        
        Args:
            detailed: If True, include FULL file tree + ALL dependencies.
                      Used by Planner/Implementer that need complete awareness.
                      If False, include only key findings (for fast agents).
        """
        lines = []
        lines.append("## Project Environment Snapshot")
        lines.append(f"Language: {self.language}")
        lines.append(f"Files: {self.total_files} across {self.total_dirs} directories")
        
        if self.frameworks:
            lines.append(f"Frameworks: {', '.join(self.frameworks)}")
        
        if self.auth_systems:
            lines.append(f"Auth System: {', '.join(self.auth_systems)}")
        
        if self.databases:
            lines.append(f"Database: {', '.join(self.databases)}")
        
        if self.package_manager:
            lines.append(f"Package Manager: {self.package_manager}")
        
        if self.test_runner:
            lines.append(f"Test Runner: {self.test_runner}")
        
        if self.build_tool:
            lines.append(f"Build Tool: {self.build_tool}")
        
        if self.has_docker:
            lines.append("Containerized: Docker")
        
        if self.has_ci:
            lines.append(f"CI/CD: {self.ci_platform}")
        
        if self.env_keys:
            lines.append(f"Environment Variables: {', '.join(self.env_keys[:15])}")
        
        if self.entry_points:
            lines.append(f"Entry Points: {', '.join(self.entry_points[:5])}")
        
        if detailed:
            # ── DETAILED MODE: Full project map for Planner/Implementer ──
            
            # ALL dependencies with versions
            if self.dependencies:
                lines.append("\n### Dependencies")
                for name, version in sorted(self.dependencies.items()):
                    lines.append(f"  {name}: {version}" if version else f"  {name}")
            
            if self.dev_dependencies:
                lines.append("\n### Dev Dependencies")
                for name, version in sorted(self.dev_dependencies.items()):
                    lines.append(f"  {name}: {version}" if version else f"  {name}")
            
            # File tree with sizes (capped at 500 to stay within token budget)
            max_files = 500
            lines.append("\n### Complete File Tree")
            for entry in self.file_tree[:max_files]:
                size_kb = entry.size_bytes / 1024
                if size_kb >= 1:
                    lines.append(f"  {entry.path} ({size_kb:.1f}KB)")
                else:
                    lines.append(f"  {entry.path} ({entry.size_bytes}B)")
            if len(self.file_tree) > max_files:
                lines.append(f"  ... and {len(self.file_tree) - max_files} more files")
            
            # Config files
            if self.config_files:
                lines.append(f"\n### Config Files: {', '.join(self.config_files)}")
            
        else:
            # ── LEAN MODE: Key findings only for fast agents ──
            
            # Key dependencies (top 15 only)
            if self.dependencies:
                top_deps = list(self.dependencies.items())[:15]
                dep_str = ", ".join(f"{k}@{v}" if v else k for k, v in top_deps)
                lines.append(f"Key Dependencies: {dep_str}")
            
            # Directory structure (compact)
            if self.dir_tree:
                lines.append("\nDirectory Structure:")
                for d in self.dir_tree[:20]:
                    lines.append(f"  {d}/")
        
        return "\n".join(lines)


# ── Scanner ──────────────────────────────────────────────

class ProjectScanner:
    """Scans a project for comprehensive environment context.
    
    Runs BEFORE all other agents to give them full project awareness.
    Fast — uses only filesystem reads, no LLM calls.
    """
    
    def __init__(self, repo_path: str, language: str = "", max_files: int = 5000):
        self.repo_path = Path(repo_path)
        self.language = language
        self.max_files = max_files  # Safety cap — stops scanning after this many files
        self.logger = get_logger("scanner")
        self._all_imports: set = set()
        self._all_file_content_cache: Dict[str, str] = {}
        self._cache_total_bytes: int = 0
        self._cache_max_bytes: int = 5 * 1024 * 1024  # 5MB total cap
    
    def scan(self) -> ProjectSnapshot:
        """Run the full project scan. Returns a ProjectSnapshot."""
        snapshot = ProjectSnapshot(language=self.language)
        
        # Step 1: Walk file tree
        self._scan_file_tree(snapshot)
        
        # If the scan was truncated (too many files), skip expensive steps
        if snapshot.total_files >= self.max_files:
            self.logger.warning(
                f"File tree truncated at {self.max_files} files — "
                f"skipping import scanning to prevent hangs. "
                f"Tip: point --repo at a project directory, not your home folder.",
                extra={"agent": "scanner", "step": "truncated"},
            )
            # Still do dep detection (reads only manifest files, fast)
            self._scan_dependencies(snapshot)
            self._scan_environment(snapshot)
            self._detect_build_system(snapshot)
            self._find_entry_points(snapshot)
        else:
            # Step 2: Read dependency manifests
            self._scan_dependencies(snapshot)
            
            # Step 3: Scan imports across files (for framework/auth/db detection)
            self._scan_imports(snapshot)
            
            # Step 4: Detect frameworks
            self._detect_frameworks(snapshot)
            
            # Step 5: Detect auth systems
            self._detect_auth(snapshot)
            
            # Step 6: Detect databases
            self._detect_databases(snapshot)
            
            # Step 7: Scan environment
            self._scan_environment(snapshot)
            
            # Step 8: Detect build system
            self._detect_build_system(snapshot)
            
            # Step 9: Find entry points
            self._find_entry_points(snapshot)
        
        self.logger.info(
            f"Project scan: {snapshot.total_files} files, "
            f"{len(snapshot.frameworks)} frameworks, "
            f"{len(snapshot.auth_systems)} auth, "
            f"{len(snapshot.databases)} db",
            extra={"agent": "scanner", "step": "scan_complete"},
        )
        
        return snapshot
    
    # ── File Tree ────────────────────────────────────────
    
    def _scan_file_tree(self, snapshot: ProjectSnapshot):
        """Walk the directory tree, respecting .gitignore-style skips."""
        dirs_seen = set()
        file_count = 0
        scan_start = time.monotonic()
        MAX_SCAN_SECONDS = 5.0  # Hard timeout — prevents hangs on huge dirs
        
        # Dot-directories that are useful and should NOT be skipped
        KEEP_DOT_DIRS = {".github", ".gitlab", ".circleci", ".docker"}
        
        for root, dirs, files in os.walk(self.repo_path):
            # Time-based circuit breaker
            if time.monotonic() - scan_start > MAX_SCAN_SECONDS:
                self.logger.warning(
                    f"Scan timed out after {MAX_SCAN_SECONDS}s — directory too large",
                    extra={"agent": "scanner", "step": "timeout"},
                )
                break
            
            # Skip ignored directories, but keep CI/CD dot-dirs
            dirs[:] = [
                d for d in dirs
                if d not in SKIP_DIRS and (
                    not d.startswith(".") or d in KEEP_DOT_DIRS
                )
            ]
            
            rel_root = os.path.relpath(root, self.repo_path)
            if rel_root != ".":
                dirs_seen.add(rel_root.replace("\\", "/"))
            
            for fname in files:
                if fname in SKIP_FILES:
                    continue
                
                # Safety cap — prevent hangs on huge directories
                if file_count >= self.max_files:
                    snapshot.total_files = file_count
                    snapshot.dir_tree = sorted(dirs_seen)
                    snapshot.total_dirs = len(dirs_seen) + 1
                    return  # Stop walking
                
                fpath = Path(root) / fname
                try:
                    size = fpath.stat().st_size
                except OSError:
                    size = 0
                
                rel_path = os.path.relpath(fpath, self.repo_path).replace("\\", "/")
                lang = self._detect_file_language(fname)
                
                snapshot.file_tree.append(FileEntry(
                    path=rel_path, size_bytes=size, language=lang,
                ))
                file_count += 1
        
        snapshot.total_files = len(snapshot.file_tree)
        snapshot.dir_tree = sorted(dirs_seen)
        snapshot.total_dirs = len(dirs_seen) + 1  # +1 for root
    
    def _detect_file_language(self, filename: str) -> str:
        """Detect language from file extension."""
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "typescript", ".jsx": "javascript",
            ".go": "go", ".rs": "rust", ".java": "java",
            ".cpp": "cpp", ".c": "c", ".cs": "csharp",
            ".rb": "ruby", ".php": "php", ".swift": "swift",
            ".kt": "kotlin", ".dart": "dart",
            ".html": "html", ".css": "css", ".scss": "scss",
            ".json": "json", ".yaml": "yaml", ".yml": "yaml",
            ".md": "markdown", ".sql": "sql",
        }
        ext = Path(filename).suffix.lower()
        return ext_map.get(ext, "")
    
    # ── Dependencies ─────────────────────────────────────
    
    def _scan_dependencies(self, snapshot: ProjectSnapshot):
        """Read dependency manifests (package.json, requirements.txt, etc.)."""
        
        # package.json (Node.js)
        pkg_json = self.repo_path / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                snapshot.dependencies.update(data.get("dependencies", {}))
                snapshot.dev_dependencies.update(data.get("devDependencies", {}))
                snapshot.config_files.append("package.json")
            except (json.JSONDecodeError, OSError):
                pass
        
        # requirements.txt (Python)
        req_txt = self.repo_path / "requirements.txt"
        if req_txt.exists():
            try:
                for line in req_txt.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        # Parse "package==version" or "package>=version"
                        match = re.match(r'^([a-zA-Z0-9_.-]+)\s*([><=!~]+\s*.+)?', line)
                        if match:
                            name = match.group(1)
                            version = (match.group(2) or "").strip()
                            snapshot.dependencies[name] = version
                snapshot.config_files.append("requirements.txt")
            except OSError:
                pass
        
        # pyproject.toml (Python/Poetry)
        pyproject = self.repo_path / "pyproject.toml"
        if pyproject.exists():
            snapshot.config_files.append("pyproject.toml")
            try:
                content = pyproject.read_text(encoding="utf-8", errors="ignore")
                # Simple regex parsing (avoids toml dependency)
                deps = re.findall(r'^([a-zA-Z0-9_-]+)\s*=\s*["\']([^"\']+)', content, re.MULTILINE)
                for name, version in deps:
                    if name not in ("python", "name", "version", "description"):
                        snapshot.dependencies[name] = version
            except OSError:
                pass
        
        # go.mod (Go)
        go_mod = self.repo_path / "go.mod"
        if go_mod.exists():
            try:
                content = go_mod.read_text(encoding="utf-8", errors="ignore")
                requires = re.findall(r'^\s*(\S+)\s+(v\S+)', content, re.MULTILINE)
                for name, version in requires:
                    snapshot.dependencies[name] = version
                snapshot.config_files.append("go.mod")
            except OSError:
                pass
        
        # Cargo.toml (Rust)
        cargo = self.repo_path / "Cargo.toml"
        if cargo.exists():
            snapshot.config_files.append("Cargo.toml")
        
        # pom.xml (Java/Maven)
        pom = self.repo_path / "pom.xml"
        if pom.exists():
            snapshot.config_files.append("pom.xml")
    
    # ── Import Scanning ──────────────────────────────────
    
    def _scan_imports(self, snapshot: ProjectSnapshot):
        """Scan source files for import statements."""
        code_extensions = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java"}
        
        for entry in snapshot.file_tree:
            ext = Path(entry.path).suffix.lower()
            if ext not in code_extensions:
                continue
            if entry.size_bytes > 500_000:  # Skip huge files
                continue
            
            fpath = self.repo_path / entry.path
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                # Cap per-file cache at 5KB, total cache at 5MB
                snippet = content[:5000]
                if self._cache_total_bytes + len(snippet) <= self._cache_max_bytes:
                    self._all_file_content_cache[entry.path] = snippet
                    self._cache_total_bytes += len(snippet)
                
                # Extract imports
                if ext == ".py":
                    # Python: import X, from X import Y
                    imports = re.findall(r'^\s*(?:import|from)\s+([a-zA-Z0-9_.]+)', content, re.MULTILINE)
                    self._all_imports.update(imports)
                elif ext in (".js", ".ts", ".tsx", ".jsx"):
                    # JS/TS: import ... from "X", require("X")
                    imports = re.findall(r'(?:from|require\()\s*["\']([^"\']+)', content)
                    self._all_imports.update(imports)
                elif ext == ".go":
                    # Go: import "X"
                    imports = re.findall(r'import\s+(?:\(([^)]+)\)|"([^"]+)")', content, re.DOTALL)
                    for group_imports, single_import in imports:
                        if single_import:
                            self._all_imports.add(single_import)
                        if group_imports:
                            for line in group_imports.splitlines():
                                match = re.search(r'"([^"]+)"', line)
                                if match:
                                    self._all_imports.add(match.group(1))
            except OSError:
                pass
    
    # ── Framework Detection ──────────────────────────────
    
    def _detect_frameworks(self, snapshot: ProjectSnapshot):
        """Detect frameworks from imports and dependencies."""
        all_deps = set(snapshot.dependencies.keys()) | set(snapshot.dev_dependencies.keys())
        
        for framework, sigs in FRAMEWORK_SIGNATURES.items():
            # Check imports
            if any(imp in self._all_imports or
                   any(imp in i for i in self._all_imports)
                   for imp in sigs["imports"]):
                snapshot.frameworks.append(framework)
                continue
            
            # Check dependency manifest
            if any(dep in all_deps for dep in sigs["deps"]):
                snapshot.frameworks.append(framework)
    
    # ── Auth Detection ───────────────────────────────────
    
    def _detect_auth(self, snapshot: ProjectSnapshot):
        """Detect authentication systems."""
        all_deps = set(snapshot.dependencies.keys()) | set(snapshot.dev_dependencies.keys())
        all_files = {e.path.lower() for e in snapshot.file_tree}
        
        for auth, sigs in AUTH_SIGNATURES.items():
            # Check imports
            if any(imp in self._all_imports or
                   any(imp in i for i in self._all_imports)
                   for imp in sigs["imports"]):
                snapshot.auth_systems.append(auth)
                continue
            
            # Check deps
            if any(dep in all_deps for dep in sigs.get("imports", [])):
                snapshot.auth_systems.append(auth)
                continue
            
            # Check for auth-related files
            if any(f in file_path for f in sigs.get("files", []) for file_path in all_files):
                snapshot.auth_systems.append(auth)
    
    # ── Database Detection ───────────────────────────────
    
    def _detect_databases(self, snapshot: ProjectSnapshot):
        """Detect databases from imports and dependencies."""
        all_deps = set(snapshot.dependencies.keys()) | set(snapshot.dev_dependencies.keys())
        
        for db, sigs in DB_SIGNATURES.items():
            if any(imp in self._all_imports or
                   any(imp in i for i in self._all_imports)
                   for imp in sigs["imports"]):
                snapshot.databases.append(db)
                continue
            
            if any(dep in all_deps for dep in sigs["deps"]):
                snapshot.databases.append(db)
                continue
            
            # Check for DB-specific files
            for f_pattern in sigs.get("files", []):
                if any(f_pattern in e.path for e in snapshot.file_tree):
                    snapshot.databases.append(db)
                    break
    
    # ── Environment ──────────────────────────────────────
    
    def _scan_environment(self, snapshot: ProjectSnapshot):
        """Scan .env files (keys only), Docker, CI/CD."""
        
        # .env files — extract KEY NAMES only, NEVER values
        for env_name in [".env", ".env.local", ".env.example", ".env.development"]:
            env_file = self.repo_path / env_name
            if env_file.exists():
                try:
                    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key = line.split("=", 1)[0].strip()
                            if key and key not in snapshot.env_keys:
                                snapshot.env_keys.append(key)
                except OSError:
                    pass
        
        # Docker
        snapshot.has_docker = (
            (self.repo_path / "Dockerfile").exists() or
            (self.repo_path / "docker-compose.yml").exists() or
            (self.repo_path / "docker-compose.yaml").exists() or
            (self.repo_path / "compose.yml").exists()
        )
        if snapshot.has_docker:
            snapshot.config_files.append("Dockerfile")
        
        # CI/CD detection
        if (self.repo_path / ".github" / "workflows").is_dir():
            snapshot.has_ci = True
            snapshot.ci_platform = "github_actions"
            snapshot.config_files.append(".github/workflows/")
        elif (self.repo_path / ".gitlab-ci.yml").exists():
            snapshot.has_ci = True
            snapshot.ci_platform = "gitlab_ci"
        elif (self.repo_path / "Jenkinsfile").exists():
            snapshot.has_ci = True
            snapshot.ci_platform = "jenkins"
        elif (self.repo_path / ".circleci").is_dir():
            snapshot.has_ci = True
            snapshot.ci_platform = "circleci"
    
    # ── Build System ─────────────────────────────────────
    
    def _detect_build_system(self, snapshot: ProjectSnapshot):
        """Detect package manager, build tool, and test runner."""
        
        # Package manager
        if (self.repo_path / "pnpm-lock.yaml").exists():
            snapshot.package_manager = "pnpm"
        elif (self.repo_path / "yarn.lock").exists():
            snapshot.package_manager = "yarn"
        elif (self.repo_path / "bun.lockb").exists():
            snapshot.package_manager = "bun"
        elif (self.repo_path / "package-lock.json").exists():
            snapshot.package_manager = "npm"
        elif (self.repo_path / "poetry.lock").exists():
            snapshot.package_manager = "poetry"
        elif (self.repo_path / "uv.lock").exists():
            snapshot.package_manager = "uv"
        elif (self.repo_path / "Pipfile.lock").exists():
            snapshot.package_manager = "pipenv"
        elif (self.repo_path / "requirements.txt").exists():
            snapshot.package_manager = "pip"
        elif (self.repo_path / "go.sum").exists():
            snapshot.package_manager = "go modules"
        
        # Build tool
        all_deps = set(snapshot.dependencies.keys()) | set(snapshot.dev_dependencies.keys())
        if "vite" in all_deps:
            snapshot.build_tool = "vite"
        elif "webpack" in all_deps:
            snapshot.build_tool = "webpack"
        elif "esbuild" in all_deps:
            snapshot.build_tool = "esbuild"
        elif "turbo" in all_deps or (self.repo_path / "turbo.json").exists():
            snapshot.build_tool = "turborepo"
        elif (self.repo_path / "Makefile").exists():
            snapshot.build_tool = "make"
        elif (self.repo_path / "setup.py").exists():
            snapshot.build_tool = "setuptools"
        
        # Test runner
        if "jest" in all_deps:
            snapshot.test_runner = "jest"
        elif "vitest" in all_deps:
            snapshot.test_runner = "vitest"
        elif "mocha" in all_deps:
            snapshot.test_runner = "mocha"
        elif "pytest" in all_deps or "pytest" in snapshot.dependencies:
            snapshot.test_runner = "pytest"
        elif any("pytest" in i for i in self._all_imports):
            snapshot.test_runner = "pytest"
        elif any("unittest" in i for i in self._all_imports):
            snapshot.test_runner = "unittest"
        elif (self.repo_path / "go.mod").exists():
            snapshot.test_runner = "go test"
    
    # ── Entry Points ─────────────────────────────────────
    
    def _find_entry_points(self, snapshot: ProjectSnapshot):
        """Find main entry points of the project."""
        entry_candidates = [
            "main.py", "app.py", "server.py", "manage.py", "wsgi.py",
            "index.js", "index.ts", "server.js", "server.ts", "app.js", "app.ts",
            "main.go", "cmd/main.go",
            "src/index.js", "src/index.ts", "src/main.js", "src/main.ts",
            "src/App.tsx", "src/App.jsx", "src/app.py",
            "pages/index.tsx", "pages/index.js",
            "app/page.tsx", "app/page.js",
        ]
        
        for candidate in entry_candidates:
            if (self.repo_path / candidate).exists():
                snapshot.entry_points.append(candidate)
        
        # Check package.json scripts.start or scripts.dev
        pkg_json = self.repo_path / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                scripts = data.get("scripts", {})
                if "start" in scripts:
                    snapshot.entry_points.append(f"npm start -> {scripts['start']}")
                if "dev" in scripts:
                    snapshot.entry_points.append(f"npm run dev -> {scripts['dev']}")
            except (json.JSONDecodeError, OSError):
                pass
