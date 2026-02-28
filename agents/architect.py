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
    
    def _suggest_target_location(
        self, 
        repo_path: Path, 
        language: str,
        user_request: str
    ) -> tuple:
        """Suggest where new code should be placed."""
        request_lower = user_request.lower()
        
        # Map request keywords to typical directories
        dir_hints = {
            "auth": ["internal/auth", "pkg/auth", "src/auth", "lib/auth"],
            "middleware": ["internal/middleware", "middleware", "src/middleware"],
            "api": ["internal/api", "api", "pkg/api", "src/api"],
            "database": ["internal/db", "pkg/db", "src/db", "internal/database"],
            "config": ["internal/config", "pkg/config", "src/config"],
            "user": ["internal/user", "pkg/user", "src/user", "internal/users"],
            "test": ["tests", "test", "internal/test"],
        }
        
        for keyword, dirs in dir_hints.items():
            if keyword in request_lower:
                for dir_path in dirs:
                    if (repo_path / dir_path).exists():
                        ext_lookup = {
                            "go": ".go", "python": ".py", "typescript": ".ts",
                            "javascript": ".js", "cpp": ".cpp", "c": ".c", "java": ".java",
                        }
                        ext = ext_lookup.get(language, ".py")
                        feature_name = self._extract_feature_name(request_lower)
                        return f"{dir_path}/{feature_name}{ext}", dir_path
        
        # Default: src/ or internal/ or root
        feature_name = self._extract_feature_name(request_lower)
        ext_lookup = {
            "go": ".go", "python": ".py", "typescript": ".ts",
            "javascript": ".js", "cpp": ".cpp", "c": ".c", "java": ".java",
        }
        if (repo_path / "internal").exists():
            ext = ext_lookup.get(language, ".py")
            return f"internal/{feature_name}{ext}", "internal"
        if (repo_path / "src").exists():
            ext = ext_lookup.get(language, ".py")
            return f"src/{feature_name}{ext}", "src"
        
        feature_name = self._extract_feature_name(request_lower)
        ext_lookup = {
            "go": ".go", "python": ".py", "typescript": ".ts",
            "javascript": ".js", "cpp": ".cpp", "c": ".c", "java": ".java",
        }
        ext = ext_lookup.get(language, ".py")
        return f"{feature_name}{ext}", ""
    
    def _extract_feature_name(self, request: str) -> str:
        """Extract a descriptive snake_case filename from the user request."""
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
        name_words = words[:3] if words else ["feature"]
        name = "_".join(name_words)
        
        # Ensure valid Python identifier (no leading digits)
        if name and name[0].isdigit():
            name = f"mod_{name}"
        
        return name or "feature"
    
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
