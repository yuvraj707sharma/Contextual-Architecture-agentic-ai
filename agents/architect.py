"""
Architect Agent - Maps codebase structure and identifies utilities.

The Architect Agent is the "navigator" of the system. It:
1. Walks the directory tree to understand project structure
2. Identifies existing utilities that can be reused
3. Determines where new code should be placed
4. Maps dependency relationships
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

from .base import BaseAgent, AgentContext, AgentResponse, AgentRole
from .context_budget import estimate_tokens, truncate_to_tokens


@dataclass
class FileInfo:
    """Information about a file in the project."""
    path: str
    relative_path: str
    language: str
    size_bytes: int
    exports: List[str] = field(default_factory=list)  # Exported functions/classes
    imports: List[str] = field(default_factory=list)  # What it imports
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "language": self.language,
            "size_bytes": self.size_bytes,
            "exports": self.exports,
            "imports": self.imports,
        }


@dataclass
class ArchitectOutput:
    """Structured output from the Architect Agent."""
    
    # Suggested target file for the new code
    target_file: str = ""
    
    # Suggested package/module for the new code
    target_package: str = ""
    
    # Existing utilities that could be reused
    existing_utilities: List[Dict[str, str]] = field(default_factory=list)
    
    # Imports the new code will need
    imports_needed: List[str] = field(default_factory=list)
    
    # Project structure map
    structure: Dict[str, List[str]] = field(default_factory=dict)
    
    # Related files that might need modification
    related_files: List[str] = field(default_factory=list)
    
    # Key configuration files found
    config_files: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_file": self.target_file,
            "target_package": self.target_package,
            "existing_utilities": self.existing_utilities,
            "imports_needed": self.imports_needed,
            "structure": self.structure,
            "related_files": self.related_files,
            "config_files": self.config_files,
        }
    
    def to_prompt_context(self, max_tokens: int = 0) -> str:
        """Convert to string for LLM prompts.
        
        V2: Returns focused output (diff not map).
        Only target file + top 3 utilities + top 3 related files.
        The full directory tree is noise for the Implementer.
        
        Args:
            max_tokens: If > 0, truncate output to fit this token budget.
        """
        parts = []
        
        if self.target_file:
            parts.append(f"## Target File\n`{self.target_file}`")
        
        if self.target_package:
            parts.append(f"\n## Target Package\n`{self.target_package}`")
        
        if self.existing_utilities:
            parts.append("\n## Existing Utilities to Reuse")
            # V2: Only top 3 most relevant utilities (not all 15)
            for util in self.existing_utilities[:3]:
                parts.append(f"- `{util['name']}` in `{util['file']}`: {util.get('description', '')}")
            if len(self.existing_utilities) > 3:
                parts.append(f"  _(+{len(self.existing_utilities) - 3} more, showing top 3)_")
        
        if self.imports_needed:
            parts.append("\n## Imports Needed")
            for imp in self.imports_needed:
                parts.append(f"- `{imp}`")
        
        if self.related_files:
            parts.append("\n## Related Files")
            # V2: Only top 3 related files (not 10)
            for f in self.related_files[:3]:
                parts.append(f"- `{f}`")
        
        # V2: Skip full structure dump — the Implementer doesn't need to know
        # about tests/fixtures/mock_data.json when writing a feature.
        if self.structure and not self.target_file:
            parts.append("\n## Project Layout (summary)")
            for dir_name, files in list(self.structure.items())[:3]:
                parts.append(f"- **{dir_name}/**: {len(files)} files")
        
        result = "\n".join(parts)
        
        if max_tokens > 0:
            result = truncate_to_tokens(result, max_tokens)
        
        return result


class ArchitectAgent(BaseAgent):
    """
    Agent that maps codebase structure and identifies utilities.
    
    The Architect provides:
    - Where new code should be placed
    - Existing utilities to import/reuse
    - Project structure understanding
    - Dependency mapping
    """
    
    SYSTEM_PROMPT = None  # Loaded from system_prompts module
    
    @classmethod
    def _load_prompt(cls) -> str:
        from .system_prompts import ARCHITECT_SYSTEM_PROMPT
        return ARCHITECT_SYSTEM_PROMPT
    
    # File extensions for each language
    LANG_EXTENSIONS = {
        "go": [".go"],
        "python": [".py"],
        "typescript": [".ts", ".tsx"],
        "javascript": [".js", ".jsx"],
        "cpp": [".cpp", ".cc", ".cxx", ".h", ".hpp"],
        "c": [".c", ".h"],
        "java": [".java"],
    }
    
    # Directories to ignore
    IGNORE_DIRS = {
        "node_modules", "vendor", ".git", "__pycache__", 
        ".venv", "venv", "dist", "build", ".next"
    }
    
    def __init__(self, llm_client=None):
        super().__init__(llm_client)
    
    @property
    def role(self) -> AgentRole:
        return AgentRole.ARCHITECT
    
    @property
    def system_prompt(self) -> str:
        return self._load_prompt()
    
    async def process(self, context: AgentContext) -> AgentResponse:
        """
        Analyze project structure and suggest where new code belongs.
        """
        output = ArchitectOutput()
        
        try:
            repo_path = Path(context.repo_path)
            
            if not repo_path.exists():
                return self._create_response(
                    success=False,
                    data={},
                    summary=f"Repository path does not exist: {context.repo_path}",
                    errors=["Invalid repository path"],
                )
            
            # Step 1: Map directory structure
            output.structure = self._map_structure(repo_path)
            
            # Step 2: Find config files
            output.config_files = self._find_config_files(repo_path)
            
            # Step 3: Find existing utilities
            output.existing_utilities = self._find_utilities(
                repo_path, context.language, context.user_request
            )
            
            # Step 4: Suggest target file location
            output.target_file, output.target_package = self._suggest_target_location(
                repo_path, context.language, context.user_request
            )
            
            # Step 5: Determine needed imports
            output.imports_needed = self._determine_imports(
                output.existing_utilities, context.language
            )
            
            # Step 6: Find related files
            output.related_files = self._find_related_files(
                repo_path, context.user_request, context.language
            )
            
            return self._create_response(
                success=True,
                data=output.to_dict(),
                summary=self._generate_summary(output),
                next_agent=AgentRole.IMPLEMENTER,
            )
            
        except Exception as e:
            return self._create_response(
                success=False,
                data={},
                summary=f"Failed to analyze structure: {str(e)}",
                errors=[str(e)],
            )
    
    def _map_structure(self, repo_path: Path) -> Dict[str, List[str]]:
        """Map the directory structure of the project."""
        structure = {}
        
        for item in repo_path.iterdir():
            if item.is_dir() and item.name not in self.IGNORE_DIRS and not item.name.startswith('.'):
                # Get immediate children
                children = []
                try:
                    for child in item.iterdir():
                        if child.is_dir():
                            children.append(f"{child.name}/")
                        elif child.is_file():
                            children.append(child.name)
                except PermissionError:
                    continue
                
                structure[item.name] = children[:20]  # Limit per directory
        
        return structure
    
    def _find_config_files(self, repo_path: Path) -> List[str]:
        """Find configuration files in the project."""
        config_patterns = [
            "*.toml", "*.yaml", "*.yml", "*.json", "*.ini",
            ".env*", "Makefile", "Dockerfile", "*.config.js", "*.config.ts"
        ]
        
        config_files = []
        for pattern in config_patterns:
            for f in repo_path.glob(pattern):
                if f.is_file() and not any(p in str(f) for p in self.IGNORE_DIRS):
                    config_files.append(str(f.relative_to(repo_path)))
        
        return config_files[:20]  # Limit
    
    def _find_utilities(
        self, 
        repo_path: Path, 
        language: str,
        user_request: str
    ) -> List[Dict[str, str]]:
        """Find existing utilities that could be reused.
        
        V2: Returns only top 3 most relevant utilities (not all 15).
        """
        utilities = []
        extensions = self.LANG_EXTENSIONS.get(language, [])
        
        # Keywords from user request
        keywords = set(user_request.lower().split())
        common_util_words = {"auth", "jwt", "token", "user", "config", "db", "database", 
                            "http", "client", "logger", "log", "error", "validator", "validate"}
        relevant_keywords = keywords & common_util_words
        
        # Scan files for exports
        for ext in extensions:
            for file_path in list(repo_path.rglob(f"*{ext}"))[:100]:
                # Skip ignored dirs
                if any(ignored in str(file_path) for ignored in self.IGNORE_DIRS):
                    continue
                
                try:
                    exports = self._extract_exports(file_path, language)
                    
                    for export in exports:
                        export_lower = export.lower()
                        # Check if export is relevant to user request
                        if any(kw in export_lower for kw in relevant_keywords):
                            utilities.append({
                                "name": export,
                                "file": str(file_path.relative_to(repo_path)),
                                "description": f"Exported {export}",
                            })
                except Exception:
                    continue
        
        return utilities[:3]  # V2: Top 3 only (was 15)
    
    def _extract_exports(self, file_path: Path, language: str) -> List[str]:
        """Extract exported functions/classes from a file."""
        exports = []
        
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return exports
        
        if language == "go":
            # Go: Exported = starts with uppercase
            pattern = r'func\s+([A-Z]\w+)\s*\('
            exports.extend(re.findall(pattern, content))
            # Types
            pattern = r'type\s+([A-Z]\w+)\s+'
            exports.extend(re.findall(pattern, content))
            
        elif language == "python":
            # Python: Classes and top-level functions
            pattern = r'^(?:def|class)\s+(\w+)'
            matches = re.findall(pattern, content, re.MULTILINE)
            # Filter out private (starts with _)
            exports.extend([m for m in matches if not m.startswith('_')])
            
        elif language in ("typescript", "javascript"):
            # TS/JS: export keyword
            pattern = r'export\s+(?:const|function|class|interface|type)\s+(\w+)'
            exports.extend(re.findall(pattern, content))
            # Default exports
            pattern = r'export\s+default\s+(?:function|class)?\s*(\w+)'
            exports.extend(re.findall(pattern, content))
        
        elif language in ("cpp", "c"):
            # C/C++: functions and classes
            pattern = r'^(?:void|int|float|double|char|bool|string|auto|unsigned|long)\s+(\w+)\s*\('
            exports.extend(re.findall(pattern, content, re.MULTILINE))
            if language == "cpp":
                pattern = r'^class\s+(\w+)'
                exports.extend(re.findall(pattern, content, re.MULTILINE))
        
        elif language == "java":
            pattern = r'public\s+(?:static\s+)?(?:void|int|String|boolean|\w+)\s+(\w+)\s*\('
            exports.extend(re.findall(pattern, content))
            pattern = r'public\s+class\s+(\w+)'
            exports.extend(re.findall(pattern, content))
        
        return list(set(exports))  # Dedupe
    
    # Banned generic filenames — forces the model to derive real names
    BANNED_FILENAMES = {
        "feature", "utils", "helpers", "misc", "stuff", "temp",
        "generated", "new_file", "code", "main_new", "module",
    }
    
    def _suggest_target_location(
        self, 
        repo_path: Path, 
        language: str,
        user_request: str
    ) -> tuple:
        """Suggest where new code should be placed.
        
        V3: Routing, not generation.
        Priority order:
          1. Find an EXISTING file that's the logical home (MODIFY > CREATE)
          2. If no match, create in the right directory with a sibling-derived name
          3. NEVER output a banned generic filename
        """
        request_lower = user_request.lower()
        ext_lookup = {
            "go": ".go", "python": ".py", "typescript": ".ts",
            "javascript": ".js", "cpp": ".cpp", "c": ".c", "java": ".java",
        }
        ext = ext_lookup.get(language, ".py")
        
        # ── Step 1: Try to route to an EXISTING file ─────────────
        existing = self._find_best_existing_file(repo_path, language, request_lower)
        if existing:
            rel = str(existing.relative_to(repo_path))
            package = str(existing.parent.relative_to(repo_path)) if existing.parent != repo_path else ""
            return rel, package
        
        # ── Step 2: No existing match — create in best directory ─
        # Map request keywords to typical directories
        dir_hints = {
            "auth": ["internal/auth", "pkg/auth", "src/auth", "lib/auth", "auth"],
            "middleware": ["internal/middleware", "middleware", "src/middleware"],
            "api": ["internal/api", "api", "pkg/api", "src/api", "routes", "routers"],
            "database": ["internal/db", "pkg/db", "src/db", "internal/database", "db", "models"],
            "config": ["internal/config", "pkg/config", "src/config", "config"],
            "user": ["internal/user", "pkg/user", "src/user", "internal/users", "users"],
            "test": ["tests", "test", "internal/test"],
            "rate": ["internal/middleware", "middleware", "src/middleware"],
            "limit": ["internal/middleware", "middleware", "src/middleware"],
            "cache": ["internal/cache", "cache", "src/cache", "pkg/cache"],
            "log": ["internal/logger", "logger", "src/logger", "logging"],
            "email": ["internal/email", "email", "src/email", "notifications"],
            "payment": ["internal/payment", "payment", "src/payment", "billing"],
            "webhook": ["internal/webhook", "webhook", "src/webhook", "hooks"],
        }
        
        feature_name = self._extract_feature_name(request_lower, repo_path, language)
        
        for keyword, dirs in dir_hints.items():
            if keyword in request_lower:
                for dir_path in dirs:
                    if (repo_path / dir_path).exists():
                        # Derive name from sibling files in this directory
                        sibling_name = self._derive_sibling_name(
                            repo_path / dir_path, feature_name, ext
                        )
                        return f"{dir_path}/{sibling_name}{ext}", dir_path
        
        # Fallback: src/ or internal/ or root
        for base_dir in ["internal", "src", "lib", "pkg", "app"]:
            if (repo_path / base_dir).exists():
                sibling_name = self._derive_sibling_name(
                    repo_path / base_dir, feature_name, ext
                )
                return f"{base_dir}/{sibling_name}{ext}", base_dir
        
        # Absolute last resort: root directory
        return f"{feature_name}{ext}", ""
    
    def _find_best_existing_file(
        self,
        repo_path: Path,
        language: str,
        request_lower: str,
    ) -> Optional[Path]:
        """Find an existing file that's the best home for new code.
        
        Returns the file if a strong match exists, None otherwise.
        'Strong match' = filename contains 2+ keywords from the request,
        or exactly matches the domain concept.
        """
        extensions = self.LANG_EXTENSIONS.get(language, [])
        
        # Extract meaningful keywords from request
        noise = {"in", "to", "for", "of", "on", "by", "is", "be", "use",
                 "using", "with", "from", "into", "should", "must", "will",
                 "the", "an", "its", "this", "that", "all", "each", "add",
                 "create", "build", "implement", "make", "write", "fix",
                 "update", "modify", "refactor", "new", "existing",
                 "app", "project", "module", "file", "code"}
        keywords = [w for w in request_lower.split() if w not in noise and len(w) > 2]
        
        if not keywords:
            return None
        
        best_match: Optional[Path] = None
        best_score = 0
        
        for ext in extensions:
            for file_path in list(repo_path.rglob(f"*{ext}"))[:200]:
                if any(ignored in str(file_path) for ignored in self.IGNORE_DIRS):
                    continue
                
                # Score: how many request keywords appear in the filename
                fname = file_path.stem.lower().replace("_", " ").replace("-", " ")
                score = sum(1 for kw in keywords if kw in fname)
                
                # Bonus: file is in a directory that matches a keyword
                parent_name = file_path.parent.name.lower()
                if any(kw in parent_name for kw in keywords):
                    score += 0.5
                
                # Skip test files — don't route feature code to test files
                if "test" in fname and "test" not in request_lower:
                    continue
                
                if score > best_score:
                    best_score = score
                    best_match = file_path
        
        # Only return if we have a strong match (2+ keyword overlap)
        if best_score >= 2:
            return best_match
        
        # Single keyword match: only accept if it's an exact stem match
        if best_score >= 1 and best_match:
            stem = best_match.stem.lower()
            # e.g., request has "rate limiting" and file is "rate_limiter.py"
            if any(kw == stem or stem.startswith(kw) or stem.endswith(kw) for kw in keywords):
                return best_match
        
        return None
    
    def _derive_sibling_name(
        self,
        target_dir: Path,
        feature_name: str,
        ext: str,
    ) -> str:
        """Derive a filename that matches the naming style of sibling files.
        
        If directory has: auth_handler.py, auth_middleware.py
        And feature_name is 'rate_limiter'
        → Returns 'rate_limiter' (snake_case matches siblings).
        
        If directory has: AuthHandler.go, AuthMiddleware.go
        → Returns 'RateLimiter' (PascalCase matches siblings).
        """
        siblings = [f.stem for f in target_dir.iterdir()
                    if f.is_file() and f.suffix == ext
                    and f.stem.lower() not in self.BANNED_FILENAMES]
        
        if not siblings:
            return feature_name  # No siblings to learn from
        
        # Detect sibling naming convention
        snake_count = sum(1 for s in siblings if "_" in s)
        camel_count = sum(1 for s in siblings if s[0].isupper() and "_" not in s)
        kebab_count = sum(1 for s in siblings if "-" in s)
        
        if camel_count > snake_count and camel_count > kebab_count:
            # PascalCase: rate_limiter → RateLimiter
            return "".join(w.capitalize() for w in feature_name.split("_"))
        elif kebab_count > snake_count:
            # kebab-case: rate_limiter → rate-limiter
            return feature_name.replace("_", "-")
        else:
            # snake_case: already in correct format
            return feature_name
    
    def _extract_feature_name(
        self,
        request: str,
        repo_path: Optional[Path] = None,
        language: str = "python",
    ) -> str:
        """Extract a descriptive snake_case filename from the user request.
        
        V3: NEVER returns a banned generic name. If word extraction fails,
        derives a name from the request domain or existing sibling files.
        """
        request_clean = request.lower().strip()
        
        # Remove common prefixes
        for prefix in ["add ", "create ", "build ", "implement ", "make ", "write ",
                       "fix ", "refactor ", "update ", "modify "]:
            if request_clean.startswith(prefix):
                request_clean = request_clean[len(prefix):]
                break
        
        # Remove leading articles
        for article in ["a ", "an ", "the "]:
            if request_clean.startswith(article):
                request_clean = request_clean[len(article):]
                break
        
        # Take the first meaningful phrase (up to first period, comma, or 'that/which/it')
        for stop in [". ", ", ", " that ", " which ", " it ", " so ", " and "]:
            idx = request_clean.find(stop)
            if idx > 0:
                request_clean = request_clean[:idx]
        
        # Clean: keep only alphanumeric + spaces, collapse whitespace
        cleaned = re.sub(r"[^a-z0-9 ]", " ", request_clean)
        words = cleaned.split()
        
        # Filter out noise words
        noise = {"in", "to", "for", "of", "on", "by", "is", "be", "use",
                 "using", "with", "from", "into", "should", "must", "will",
                 "the", "an", "its", "this", "that", "all", "each",
                 "app", "project", "module", "file", "code", "new", "existing"}
        words = [w for w in words if w not in noise and len(w) > 1]
        
        # Take up to 3 words for the filename
        name_words = words[:3] if words else []
        name = "_".join(name_words)
        
        # ── V3: NEVER return a banned name ───────────────────────
        if not name or name in self.BANNED_FILENAMES:
            # Try domain-based fallback from the raw request
            domain_keywords = {
                "rate": "rate_limiter", "limit": "rate_limiter",
                "cache": "cache_manager", "cach": "cache_manager",
                "auth": "auth_handler", "login": "auth_handler",
                "jwt": "jwt_handler", "token": "token_handler",
                "email": "email_service", "mail": "email_service",
                "log": "logger", "logging": "logger",
                "valid": "validator", "check": "validator",
                "config": "configuration", "setting": "settings",
                "db": "database", "migrat": "migration",
                "webhook": "webhook_handler", "hook": "hook_handler",
                "payment": "payment_processor", "billing": "billing_service",
                "upload": "file_upload", "download": "file_download",
                "search": "search_engine", "queue": "task_queue",
                "notify": "notification_service", "alert": "alert_service",
                "schedule": "scheduler", "cron": "scheduler",
                "test": "test_suite", "health": "health_check",
                "metric": "metrics", "monitor": "monitoring",
            }
            for keyword, fallback_name in domain_keywords.items():
                if keyword in request_clean:
                    name = fallback_name
                    break
            
            # Still nothing — use first two content words regardless of length
            if not name or name in self.BANNED_FILENAMES:
                raw_words = [w for w in cleaned.split() if len(w) > 1]
                if raw_words:
                    name = "_".join(raw_words[:2])
                else:
                    # Absolute last resort: timestamp-based (never "feature")
                    import time
                    name = f"impl_{int(time.time()) % 100000}"
        
        # Final safety check: ensure not banned
        if name in self.BANNED_FILENAMES:
            name = f"{name}_impl"
        
        # Ensure valid identifier (no leading digits)
        if name and name[0].isdigit():
            name = f"mod_{name}"
        
        return name
    
    def _determine_imports(
        self, 
        utilities: List[Dict[str, str]], 
        language: str
    ) -> List[str]:
        """Determine what imports the new code will need."""
        imports = set()
        
        for util in utilities:
            file_path = util["file"]
            
            if language == "go":
                # Go: import the package (directory)
                package = "/".join(file_path.split("/")[:-1])
                if package:
                    imports.add(package)
                    
            elif language == "python":
                # Python: import the module
                module = file_path.replace("/", ".").replace(".py", "")
                imports.add(module)
                
            elif language in ("typescript", "javascript"):
                # TS/JS: relative import
                imports.add(f"./{file_path}")
        
        return list(imports)
    
    def _find_related_files(
        self, 
        repo_path: Path, 
        user_request: str,
        language: str
    ) -> List[str]:
        """Find files that might be related to the user's request.
        
        V2: Returns only top 3 most related files (not 10).
        """
        related = []
        request_lower = user_request.lower()
        
        extensions = self.LANG_EXTENSIONS.get(language, [])
        
        keywords = []
        for word in request_lower.split():
            if len(word) > 3:
                keywords.append(word)
        
        for ext in extensions:
            for file_path in list(repo_path.rglob(f"*{ext}"))[:200]:
                if any(ignored in str(file_path) for ignored in self.IGNORE_DIRS):
                    continue
                
                file_name_lower = file_path.name.lower()
                
                # Check if filename contains any keyword
                if any(kw in file_name_lower for kw in keywords):
                    related.append(str(file_path.relative_to(repo_path)))
        
        return related[:3]  # V2: Top 3 only (was 10)
    
    def _generate_summary(self, output: ArchitectOutput) -> str:
        """Generate a human-readable summary."""
        parts = []
        
        if output.target_file:
            parts.append(f"Target: {output.target_file}")
        
        if output.existing_utilities:
            parts.append(f"{len(output.existing_utilities)} utilities found")
        
        if output.imports_needed:
            parts.append(f"{len(output.imports_needed)} imports needed")
        
        if output.structure:
            parts.append(f"{len(output.structure)} directories mapped")
        
        return ". ".join(parts) if parts else "Structure analyzed"
