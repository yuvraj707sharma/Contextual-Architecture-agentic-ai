"""
Historian Agent - Analyzes PR history and project patterns.

The Historian Agent is the "memory" of the system. It:
1. Searches for relevant PRs in the project's history
2. Extracts patterns from past code reviews
3. Identifies company-specific conventions
4. Provides context to the Implementer about "how we do things here"
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from .base import BaseAgent, AgentContext, AgentResponse, AgentRole
from .context_budget import estimate_tokens, truncate_to_tokens


@dataclass
class PatternMatch:
    """A pattern found in the project's history."""
    
    # Source of the pattern (PR number, file path, etc.)
    source: str
    
    # Type of pattern (logging, error_handling, testing, etc.)
    pattern_type: str
    
    # Description of the pattern
    description: str
    
    # Example code demonstrating the pattern
    example_code: str
    
    # Confidence score (0-100)
    confidence: int = 50
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "pattern_type": self.pattern_type,
            "description": self.description,
            "example_code": self.example_code,
            "confidence": self.confidence,
        }


@dataclass
class HistorianOutput:
    """Structured output from the Historian Agent."""
    
    # Patterns found in the project
    patterns: List[PatternMatch] = field(default_factory=list)
    
    # Conventions detected (naming, structure, etc.)
    conventions: Dict[str, str] = field(default_factory=dict)
    
    # Relevant PRs found
    relevant_prs: List[Dict[str, Any]] = field(default_factory=list)
    
    # Files that are commonly modified together
    related_files: List[str] = field(default_factory=list)
    
    # Warnings about common mistakes in this codebase
    common_mistakes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "patterns": [p.to_dict() for p in self.patterns],
            "conventions": self.conventions,
            "relevant_prs": self.relevant_prs,
            "related_files": self.related_files,
            "common_mistakes": self.common_mistakes,
        }
    
    def to_prompt_context(self, max_tokens: int = 0) -> str:
        """Convert to a string for LLM prompts.
        
        Args:
            max_tokens: If > 0, truncate output to fit this token budget.
                        Patterns are included in relevance order (highest first).
        """
        parts = []
        
        if self.patterns:
            parts.append("## Detected Patterns")
            # Patterns are already sorted by relevance_score (highest first)
            for p in self.patterns:
                parts.append(f"\n### {p.pattern_type.title()} (from {p.source})")
                parts.append(f"{p.description}")
                parts.append(f"```\n{p.example_code}\n```")
        
        if self.conventions:
            parts.append("\n## Project Conventions")
            for key, value in self.conventions.items():
                parts.append(f"- **{key}**: {value}")
        
        if self.common_mistakes:
            parts.append("\n## ⚠️ Common Mistakes to Avoid")
            for mistake in self.common_mistakes:
                parts.append(f"- {mistake}")
        
        result = "\n".join(parts)
        
        if max_tokens > 0:
            result = truncate_to_tokens(result, max_tokens)
        
        return result


class HistorianAgent(BaseAgent):
    """
    Agent that analyzes PR history and project patterns.
    
    The Historian provides context about:
    - How similar features were implemented before
    - What reviewers typically ask for
    - Company-specific patterns and conventions
    - Common mistakes to avoid
    
    This context helps the Implementer write code that will
    pass review on the first attempt.
    """
    
    SYSTEM_PROMPT = None  # Loaded dynamically from system_prompts module
    
    @classmethod
    def _load_prompt(cls, complexity: str = "moderate") -> str:
        from .system_prompts import get_historian_prompt
        return get_historian_prompt(complexity)
    
    def __init__(self, llm_client=None, github_client=None, retriever=None):
        """
        Initialize the Historian Agent.
        
        Args:
            llm_client: LLM client for reasoning
            github_client: GitHub client for PR access (optional)
            retriever: CodeRetriever for RAG-based semantic pattern search (optional)
        """
        super().__init__(llm_client)
        self.github_client = github_client
        self.retriever = retriever  # RAG: semantic code search
        
        # Pattern detection rules (heuristic fallback)
        self._pattern_rules = self._build_pattern_rules()
    
    @property
    def role(self) -> AgentRole:
        return AgentRole.HISTORIAN
    
    @property
    def system_prompt(self) -> str:
        return self._load_prompt()
    
    async def process(self, context: AgentContext) -> AgentResponse:
        """
        Analyze the project history and extract relevant patterns.
        
        This runs in two modes:
        1. With LLM: Uses the LLM to reason about patterns
        2. Without LLM: Uses heuristic pattern matching (fallback)
        
        Also reads historical feedback (if available) to surface
        recurring issues and convention gaps.
        """
        output = HistorianOutput()
        
        # Load historical feedback patterns (closes the learning loop)
        try:
            from .feedback_reader import FeedbackReader
            feedback_dir = None
            if context.repo_path:
                from pathlib import Path
                feedback_dir = Path(context.repo_path) / ".contextual-architect" / "feedback"
            if feedback_dir and feedback_dir.exists():
                reader = FeedbackReader(feedback_dir)
                feedback_patterns = reader.get_historical_patterns()
                fp = feedback_patterns.get("feedback_patterns", {})
                if fp.get("total_runs_analyzed", 0) > 0:
                    context.prior_context["feedback_patterns"] = fp
                    # Surface recurring issues as anti-patterns
                    for issue in fp.get("recurring_issues", []):
                        output.common_mistakes.append(
                            f"[RECURRING x{issue['occurrences']}] {issue['issue']}"
                        )
        except Exception:
            pass  # Feedback is optional — never block the pipeline
        
        try:
            # Step 1: Search for relevant PRs (if GitHub client available)
            if self.github_client:
                output.relevant_prs = await self._search_relevant_prs(context)
            
            # Step 2: Analyze local files for patterns (heuristic)
            if context.repo_path:
                local_patterns = await self._analyze_local_patterns(context)
                output.patterns.extend(local_patterns)
            
            # Step 2.5: RAG-augmented semantic pattern search
            if self.retriever and self.retriever.indexed_count > 0:
                try:
                    rag_results = self.retriever.find_patterns(
                        context.user_request, k=8
                    )
                    for r in rag_results:
                        meta = r.get("metadata", {})
                        output.patterns.append(PatternMatch(
                            source=meta.get("file_path", "unknown"),
                            pattern_type="rag_semantic",
                            description=f"Semantically similar: {meta.get('symbol_name', 'unknown')}",
                            example_code=r.get("text", "")[:500],
                            confidence=int(r.get("relevance", 0.5) * 100),
                        ))
                    # Add formatted RAG context for LLM prompt
                    context.prior_context["rag_patterns"] = (
                        self.retriever.format_for_prompt(rag_results, max_chars=3000)
                    )
                except Exception:
                    pass  # RAG is optional — never block the pipeline
            
            # Step 3: Detect conventions from project structure
            conventions = await self._detect_conventions(context)
            output.conventions = conventions
            
            # Step 4: If LLM available, enhance with reasoning
            if self.llm_client:
                enhanced = await self._enhance_with_llm(context, output)
                output = enhanced
            
            # Step 5: Identify common mistakes
            output.common_mistakes = self._identify_common_mistakes(context, output)
            
            return self._create_response(
                success=True,
                data=output.to_dict(),
                summary=self._generate_summary(output),
                next_agent=AgentRole.ARCHITECT,
            )
            
        except Exception as e:
            return self._create_response(
                success=False,
                data={},
                summary=f"Failed to analyze history: {str(e)}",
                errors=[str(e)],
            )
    
    def _build_pattern_rules(self) -> Dict[str, List[Dict[str, Any]]]:
        """Build heuristic pattern detection rules."""
        return {
            "go": [
                {
                    "pattern_type": "error_handling",
                    "regex": r'if\s+err\s*!=\s*nil\s*{\s*return.*fmt\.Errorf\([^)]*%w',
                    "description": "Error wrapping with context",
                    "confidence": 80,
                },
                {
                    "pattern_type": "logging",
                    "regex": r'(log\.(Info|Debug|Error|Warn)\(\)|zerolog|zap\.)',
                    "description": "Structured logging",
                    "confidence": 70,
                },
                {
                    "pattern_type": "testing",
                    "regex": r'func\s+Test\w+\(t\s+\*testing\.T\)',
                    "description": "Standard Go test functions",
                    "confidence": 90,
                },
                {
                    "pattern_type": "architecture",
                    "regex": r'type\s+\w+Interface\s+interface\s*{',
                    "description": "Interface-based dependency injection",
                    "confidence": 75,
                },
            ],
            "python": [
                {
                    "pattern_type": "error_handling",
                    "regex": r'except\s+\w+Error\s+as\s+\w+:',
                    "description": "Typed exception handling",
                    "confidence": 70,
                },
                {
                    "pattern_type": "logging",
                    "regex": r'(logging\.getLogger|logger\.(info|debug|error|warning))',
                    "description": "Standard logging module",
                    "confidence": 80,
                },
                {
                    "pattern_type": "testing",
                    "regex": r'(def\s+test_\w+|@pytest\.)',
                    "description": "pytest-style tests",
                    "confidence": 85,
                },
                {
                    "pattern_type": "architecture",
                    "regex": r'(from\s+abc\s+import|@abstractmethod)',
                    "description": "Abstract base classes",
                    "confidence": 75,
                },
            ],
            "typescript": [
                {
                    "pattern_type": "error_handling",
                    "regex": r'catch\s*\(\s*\w+:\s*\w+Error\s*\)',
                    "description": "Typed error catching",
                    "confidence": 70,
                },
                {
                    "pattern_type": "architecture",
                    "regex": r'(interface\s+\w+\s*{|implements\s+\w+)',
                    "description": "Interface-based design",
                    "confidence": 80,
                },
            ],
        }
    
    async def _search_relevant_prs(self, context: AgentContext) -> List[Dict[str, Any]]:
        """Search for PRs related to the user's request."""
        # This would use the GitHub MCP to search PRs
        # For now, return empty list (will be implemented with MCP)
        return []
    
    async def _analyze_local_patterns(self, context: AgentContext) -> List[PatternMatch]:
        """
        Analyze local files for patterns using heuristics.
        
        FIXED: Now actually scans files from disk and runs regex patterns.
        V2: Adds relevance scoring — patterns are ranked by keyword overlap
            with the user request. Only top N patterns are returned.
        """
        import os
        from pathlib import Path
        
        patterns = []
        language = context.language
        
        if language not in self._pattern_rules:
            return patterns
        
        rules = self._pattern_rules[language]
        repo_path = Path(context.repo_path)
        
        if not repo_path.exists():
            return patterns
        
        # Get file extensions for this language
        ext_map = {
            "go": [".go"],
            "python": [".py"],
            "typescript": [".ts", ".tsx"],
            "javascript": [".js", ".jsx"],
            "cpp": [".cpp", ".cc", ".cxx", ".h", ".hpp"],
            "c": [".c", ".h"],
            "java": [".java"],
        }
        extensions = ext_map.get(language, [])
        
        # Find files to scan (limit to avoid scanning huge repos)
        files_to_scan = []
        for ext in extensions:
            found = list(repo_path.rglob(f"*{ext}"))
            files_to_scan.extend(found[:20])  # Max 20 files per extension
        
        # Scan each file for patterns
        for file_path in files_to_scan[:50]:  # Max 50 files total
            try:
                file_patterns = self._scan_file_for_patterns(file_path, rules)
                patterns.extend(file_patterns)
            except Exception:
                continue  # Skip files we can't read
        
        # Deduplicate patterns by type (keep highest confidence)
        seen_types = {}
        for p in patterns:
            if p.pattern_type not in seen_types or p.confidence > seen_types[p.pattern_type].confidence:
                seen_types[p.pattern_type] = p
        
        deduped = list(seen_types.values())
        
        # V2: Relevance scoring — rank patterns by keyword overlap with request
        request_words = set(context.user_request.lower().split())
        scored = []
        for p in deduped:
            pattern_words = set(p.description.lower().split())
            overlap = len(request_words & pattern_words)
            # Bonus for high-confidence patterns
            score = overlap + (p.confidence / 100.0)
            scored.append((score, p))
        
        # Sort by relevance score (highest first)
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return [p for _, p in scored]
    
    def _scan_file_for_patterns(
        self, 
        file_path: "Path", 
        rules: List[Dict[str, Any]]
    ) -> List[PatternMatch]:
        """
        Scan a single file for pattern matches.
        
        Returns PatternMatch objects with real code snippets.
        """
        patterns = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return patterns
        
        for rule in rules:
            try:
                # Find all matches of this pattern
                matches = list(re.finditer(rule["regex"], content))
                
                if matches:
                    # Get the first match as example
                    match = matches[0]
                    
                    # Extract surrounding context (the line + 1 line before/after)
                    start = max(0, content.rfind('\n', 0, match.start()) + 1)
                    end = content.find('\n', match.end())
                    if end == -1:
                        end = len(content)
                    
                    # Get a few more lines for context
                    line_start = content.rfind('\n', 0, start)
                    if line_start == -1:
                        line_start = 0
                    line_end = content.find('\n', end + 1)
                    if line_end == -1:
                        line_end = end
                    
                    code_snippet = content[line_start:line_end].strip()
                    
                    # Limit snippet length
                    if len(code_snippet) > 300:
                        code_snippet = code_snippet[:300] + "..."
                    
                    patterns.append(PatternMatch(
                        source=str(file_path.name),
                        pattern_type=rule["pattern_type"],
                        description=f"{rule['description']} (found {len(matches)} occurrences)",
                        example_code=code_snippet,
                        confidence=rule["confidence"],
                    ))
            except re.error:
                continue  # Skip invalid regex
        
        return patterns
    
    async def _detect_conventions(self, context: AgentContext) -> Dict[str, str]:
        """
        Detect project conventions from actual project structure and files.
        
        FIXED: Now scans the project to find real conventions instead of hardcoding.
        """
        from pathlib import Path
        
        conventions = {}
        repo_path = Path(context.repo_path)
        
        if not repo_path.exists():
            return self._get_default_conventions(context.language)
        
        # Detect project layout
        conventions["project_layout"] = self._detect_layout(repo_path)
        
        # Detect logging library
        conventions["logging"] = self._detect_logging_lib(repo_path, context.language)
        
        # Detect testing framework
        conventions["testing"] = self._detect_testing_framework(repo_path, context.language)
        
        # Detect import style (sample from files)
        conventions["imports"] = self._detect_import_style(repo_path, context.language)
        
        # ── GUARDRAIL: Framework/library detection ─────────────
        # When no patterns exist (no git history), scan imports to
        # identify what frameworks the project uses. This prevents
        # generating print() code for a pygame project.
        frameworks = self._detect_frameworks(repo_path, context.language)
        if frameworks:
            conventions["frameworks"] = ", ".join(frameworks)
            # Also inject into prior_context for downstream agents
            context.prior_context["detected_frameworks"] = frameworks
        
        return conventions

    def _detect_frameworks(self, repo_path, language: str) -> list:
        """Scan import statements across project files to detect frameworks."""
        from pathlib import Path
        
        # Known frameworks to detect per language
        FRAMEWORK_MAP = {
            "python": {
                "pygame": "pygame",
                "flask": "flask",
                "django": "django",
                "fastapi": "fastapi",
                "tkinter": "tkinter",
                "streamlit": "streamlit",
                "tornado": "tornado",
                "numpy": "numpy",
                "pandas": "pandas",
                "sqlalchemy": "sqlalchemy",
                "requests": "requests",
                "aiohttp": "aiohttp",
            },
            "javascript": {
                "react": "react",
                "express": "express",
                "vue": "vue",
                "next": "next",
                "angular": "angular",
            },
            "typescript": {
                "react": "react",
                "express": "express",
                "nestjs": "@nestjs",
                "next": "next",
            },
        }
        
        known = FRAMEWORK_MAP.get(language, FRAMEWORK_MAP.get("python", {}))
        detected = set()
        
        # Scan up to 20 source files
        extensions = {"python": "*.py", "javascript": "*.js", "typescript": "*.ts"}
        glob_pattern = extensions.get(language, "*.py")
        
        files_scanned = 0
        for f in repo_path.rglob(glob_pattern):
            if files_scanned >= 20:
                break
            if ".contextual-architect" in str(f) or "node_modules" in str(f):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                for framework_name, import_key in known.items():
                    if f"import {import_key}" in content or f"from {import_key}" in content:
                        detected.add(framework_name)
                files_scanned += 1
            except Exception:
                continue
        
        return sorted(detected)
    
    def _get_default_conventions(self, language: str) -> Dict[str, str]:
        """Fallback to default conventions if repo can't be analyzed."""
        defaults = {
            "go": {"project_layout": "unknown", "logging": "standard log", "testing": "testing package"},
            "python": {"project_layout": "unknown", "logging": "logging module", "testing": "unittest"},
            "typescript": {"project_layout": "unknown", "logging": "console", "testing": "unknown"},
        }
        return defaults.get(language, {"project_layout": "unknown"})
    
    def _detect_layout(self, repo_path: "Path") -> str:
        """Detect project layout from directory structure."""
        dirs = [d.name for d in repo_path.iterdir() if d.is_dir() and not d.name.startswith('.')]
        
        # Go patterns
        if "cmd" in dirs and ("internal" in dirs or "pkg" in dirs):
            return "Standard Go layout (/cmd, /internal, /pkg)"
        if "internal" in dirs:
            return "Go layout with /internal"
        
        # Python patterns
        if "src" in dirs:
            if (repo_path / "pyproject.toml").exists():
                return "src layout with pyproject.toml"
            return "src layout"
        if (repo_path / "setup.py").exists():
            return "setuptools layout"
        
        # JS/TS patterns
        if (repo_path / "package.json").exists():
            if "src" in dirs:
                return "src/ with package.json"
            return "package.json root"
        
        return f"Custom layout ({', '.join(dirs[:5])})"
    
    def _detect_logging_lib(self, repo_path: "Path", language: str) -> str:
        """Detect which logging library the project uses."""
        import re
        
        patterns = {
            "go": [
                (r'zerolog', "zerolog (structured)"),
                (r'zap\.', "zap (Uber)"),
                (r'logrus', "logrus"),
                (r'log\.(Print|Fatal|Panic)', "standard log"),
            ],
            "python": [
                (r'structlog', "structlog"),
                (r'loguru', "loguru"),
                (r'logging\.getLogger', "standard logging"),
            ],
            "typescript": [
                (r'winston', "winston"),
                (r'pino', "pino"),
                (r'console\.(log|error|warn)', "console"),
            ],
        }
        
        lang_patterns = patterns.get(language, [])
        
        # Sample a few files
        ext_map = {"go": ".go", "python": ".py", "typescript": ".ts", "cpp": ".cpp", "c": ".c", "java": ".java"}
        ext = ext_map.get(language, "")
        
        for file in list(repo_path.rglob(f"*{ext}"))[:10]:
            try:
                content = file.read_text(encoding='utf-8', errors='ignore')
                for pattern, name in lang_patterns:
                    if re.search(pattern, content):
                        return name
            except Exception:
                continue
        
        return "unknown"
    
    def _detect_testing_framework(self, repo_path: "Path", language: str) -> str:
        """Detect which testing framework the project uses."""
        # Check for config files first
        if (repo_path / "pytest.ini").exists() or (repo_path / "pyproject.toml").exists():
            try:
                content = (repo_path / "pyproject.toml").read_text(errors='ignore')
                if "pytest" in content:
                    return "pytest"
            except Exception:
                pass
        
        if (repo_path / "jest.config.js").exists() or (repo_path / "jest.config.ts").exists():
            return "jest"
        
        if (repo_path / "vitest.config.ts").exists():
            return "vitest"
        
        # Check test files
        test_files = list(repo_path.rglob("*_test.go")) + list(repo_path.rglob("test_*.py"))
        if test_files:
            return "testing package (Go)" if test_files[0].suffix == ".go" else "pytest-style"
        
        return "unknown"
    
    def _detect_import_style(self, repo_path: "Path", language: str) -> str:
        """Detect import style from sample files."""
        if language == "python":
            # Check for isort or black config
            if (repo_path / ".isort.cfg").exists():
                return "isort configured"
            if (repo_path / "pyproject.toml").exists():
                try:
                    content = (repo_path / "pyproject.toml").read_text(errors='ignore')
                    if "[tool.isort]" in content:
                        return "isort via pyproject.toml"
                except:
                    pass
        
        if language == "typescript":
            # Check for path aliases in tsconfig
            if (repo_path / "tsconfig.json").exists():
                try:
                    content = (repo_path / "tsconfig.json").read_text(errors='ignore')
                    if '"paths"' in content or '"baseUrl"' in content:
                        return "absolute imports via tsconfig paths"
                except:
                    pass
        
        return "standard"
    
    async def _enhance_with_llm(
        self, 
        context: AgentContext, 
        output: HistorianOutput
    ) -> HistorianOutput:
        """Use LLM to enhance pattern detection."""
        # When LLM is available, we would:
        # 1. Send the detected patterns + context to LLM
        # 2. Ask it to identify additional patterns
        # 3. Validate and refine existing patterns
        # For now, return as-is
        return output
    
    def _identify_common_mistakes(
        self, 
        context: AgentContext, 
        output: HistorianOutput
    ) -> List[str]:
        """Identify common mistakes based on detected patterns."""
        mistakes = []
        
        if context.language == "go":
            mistakes = [
                "Don't use naked returns in functions with named return values",
                "Always check errors - don't use _ for error returns",
                "Don't import from /internal packages of other projects",
            ]
        elif context.language == "python":
            mistakes = [
                "Don't use mutable default arguments (list, dict)",
                "Don't use bare except: clauses",
                "Don't use global state for configuration",
            ]
        elif context.language in ("typescript", "javascript"):
            mistakes = [
                "Don't use 'any' type - use proper typing",
                "Don't mutate function arguments",
                "Always handle Promise rejections",
            ]
        
        return mistakes
    
    def _generate_summary(self, output: HistorianOutput) -> str:
        """Generate a human-readable summary."""
        parts = []
        
        if output.patterns:
            parts.append(f"Found {len(output.patterns)} patterns")
        
        if output.conventions:
            parts.append(f"{len(output.conventions)} conventions detected")
        
        if output.relevant_prs:
            parts.append(f"{len(output.relevant_prs)} relevant PRs")
        
        if output.common_mistakes:
            parts.append(f"{len(output.common_mistakes)} common mistakes to avoid")
        
        return ". ".join(parts) if parts else "No patterns detected"
