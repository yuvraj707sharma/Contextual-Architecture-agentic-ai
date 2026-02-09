"""
Style Fingerprint - Extracts and enforces project-specific code style.

This module is the core innovation: instead of generating "best practice" code,
it generates code that MATCHES THE EXISTING CODEBASE.

Key Insight:
- AI tools generate "textbook" code
- Companies want code that looks like THEIR code
- The Historian detects patterns; the StyleFingerprint enforces them
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from collections import Counter


@dataclass
class StyleFingerprint:
    """
    A fingerprint of a project's coding style.
    
    This captures:
    - Naming conventions (camelCase vs snake_case)
    - Formatting preferences (spaces, indentation)
    - Import organization
    - Comment style
    - Error handling patterns
    - Logging preferences
    """
    
    # Naming
    function_naming: str = "unknown"  # camelCase, snake_case, PascalCase
    variable_naming: str = "unknown"
    class_naming: str = "unknown"
    
    # Formatting
    indent_style: str = "spaces"  # spaces or tabs
    indent_size: int = 4
    max_line_length: int = 100
    
    # Imports
    import_style: str = "grouped"  # grouped, alphabetical, random
    import_aliases: Dict[str, str] = field(default_factory=dict)  # {"fmt": "f"}
    
    # Comments
    comment_style: str = "inline"  # inline, docstring, jsdoc
    uses_todos: bool = True
    
    # Error handling
    error_style: str = "return"  # return, raise, panic
    wraps_errors: bool = True
    
    # Logging
    logger_library: str = "unknown"  # zerolog, zap, logrus, logging, console
    log_format: str = "structured"  # structured, printf, template
    
    # Testing
    test_framework: str = "unknown"
    test_naming: str = "test_"  # test_, Test, spec_
    
    # Detected patterns (raw examples)
    examples: Dict[str, List[str]] = field(default_factory=dict)
    
    def to_prompt_context(self) -> str:
        """Generate style instructions for LLM prompt."""
        lines = [
            "## Project Style Requirements (MUST FOLLOW)",
            "",
            "### Naming Conventions",
            f"- Functions: {self.function_naming}",
            f"- Variables: {self.variable_naming}",
            f"- Classes: {self.class_naming}",
            "",
            "### Formatting",
            f"- Indentation: {self.indent_size} {self.indent_style}",
            f"- Max line length: {self.max_line_length}",
            "",
            "### Error Handling",
            f"- Style: {self.error_style}",
            f"- Wrap errors with context: {'Yes' if self.wraps_errors else 'No'}",
            "",
            "### Logging",
            f"- Library: {self.logger_library}",
            f"- Format: {self.log_format}",
        ]
        
        # Add real examples
        if self.examples:
            lines.append("")
            lines.append("### Examples from This Codebase")
            for category, snippets in list(self.examples.items())[:3]:
                lines.append(f"\n**{category}:**")
                for snippet in snippets[:2]:
                    lines.append(f"```\n{snippet}\n```")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "function_naming": self.function_naming,
            "variable_naming": self.variable_naming,
            "class_naming": self.class_naming,
            "indent_style": self.indent_style,
            "indent_size": self.indent_size,
            "max_line_length": self.max_line_length,
            "import_style": self.import_style,
            "error_style": self.error_style,
            "wraps_errors": self.wraps_errors,
            "logger_library": self.logger_library,
            "log_format": self.log_format,
            "test_framework": self.test_framework,
            "test_naming": self.test_naming,
        }


class StyleAnalyzer:
    """
    Analyzes a codebase to extract its StyleFingerprint.
    
    This is the "learning" side - it reads existing code and figures out
    how this specific project is written.
    """
    
    # Common patterns for different languages
    LANG_CONFIG = {
        "python": {
            "extensions": [".py"],
            "function_pattern": r"def\s+(\w+)\s*\(",
            "class_pattern": r"class\s+(\w+)",
            "variable_pattern": r"^(\w+)\s*=",
            "import_pattern": r"^(?:from|import)\s+",
            "error_patterns": [
                (r"raise\s+\w+Error", "raise"),
                (r"try:\s*\n.*except", "try_except"),
            ],
            "logging_patterns": [
                (r"structlog", "structlog"),
                (r"loguru", "loguru"),
                (r"logging\.getLogger", "logging"),
                (r"print\(", "print"),
            ],
            "test_patterns": [
                (r"def\s+test_", "pytest"),
                (r"class\s+Test\w+.*unittest", "unittest"),
            ],
        },
        "go": {
            "extensions": [".go"],
            "function_pattern": r"func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(",
            "variable_pattern": r"(?:var|:=)\s+(\w+)",
            "error_patterns": [
                (r"if\s+err\s*!=\s*nil", "return_error"),
                (r"fmt\.Errorf\([^)]*%w", "wrap_error"),
                (r"errors\.Wrap", "pkg_errors"),
            ],
            "logging_patterns": [
                (r"zerolog", "zerolog"),
                (r"zap\.", "zap"),
                (r"logrus", "logrus"),
                (r"log\.(Print|Fatal)", "stdlib"),
            ],
            "test_patterns": [
                (r"func\s+Test\w+.*\*testing\.T", "testing"),
                (r"testify", "testify"),
            ],
        },
        "typescript": {
            "extensions": [".ts", ".tsx"],
            "function_pattern": r"(?:function|const)\s+(\w+)\s*[=\(]",
            "class_pattern": r"class\s+(\w+)",
            "variable_pattern": r"(?:const|let|var)\s+(\w+)\s*[=:]",
            "error_patterns": [
                (r"throw\s+new\s+\w+Error", "throw"),
                (r"\.catch\(", "catch"),
                (r"try\s*{", "try_catch"),
            ],
            "logging_patterns": [
                (r"winston", "winston"),
                (r"pino", "pino"),
                (r"console\.(log|error|warn)", "console"),
            ],
            "test_patterns": [
                (r"describe\(.*it\(", "jest"),
                (r"test\(", "jest"),
                (r"\.spec\.ts", "jest"),
            ],
        },
    }
    
    def __init__(self, repo_path: str, language: str):
        self.repo_path = Path(repo_path)
        self.language = language
        self.config = self.LANG_CONFIG.get(language, {})
    
    def analyze(self) -> StyleFingerprint:
        """Analyze the codebase and return a StyleFingerprint."""
        fingerprint = StyleFingerprint()
        
        if not self.config:
            return fingerprint
        
        # Collect all relevant files
        files = self._get_code_files()
        
        if not files:
            return fingerprint
        
        # Analyze naming conventions
        fingerprint.function_naming = self._detect_naming_style(files, "function")
        fingerprint.variable_naming = self._detect_naming_style(files, "variable")
        fingerprint.class_naming = self._detect_naming_style(files, "class")
        
        # Analyze formatting
        fingerprint.indent_style, fingerprint.indent_size = self._detect_indentation(files)
        fingerprint.max_line_length = self._detect_line_length(files)
        
        # Analyze error handling
        fingerprint.error_style, fingerprint.wraps_errors = self._detect_error_style(files)
        
        # Analyze logging
        fingerprint.logger_library, fingerprint.log_format = self._detect_logging(files)
        
        # Analyze testing
        fingerprint.test_framework, fingerprint.test_naming = self._detect_testing(files)
        
        # Collect examples
        fingerprint.examples = self._collect_examples(files)
        
        return fingerprint
    
    def _get_code_files(self) -> List[Path]:
        """Get all code files for this language."""
        extensions = self.config.get("extensions", [])
        files = []
        
        ignore_dirs = {
            ".git", "vendor", "node_modules", "__pycache__",
            ".venv", "venv", "dist", "build", ".next"
        }
        
        for ext in extensions:
            for f in self.repo_path.rglob(f"*{ext}"):
                if not any(ignored in str(f) for ignored in ignore_dirs):
                    files.append(f)
        
        return files[:100]  # Limit to avoid huge repos
    
    def _detect_naming_style(self, files: List[Path], name_type: str) -> str:
        """Detect naming convention (camelCase, snake_case, PascalCase)."""
        pattern_key = f"{name_type}_pattern"
        pattern = self.config.get(pattern_key)
        
        if not pattern:
            return "unknown"
        
        names = []
        for file_path in files[:30]:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                matches = re.findall(pattern, content, re.MULTILINE)
                names.extend(matches)
            except Exception:
                continue
        
        if not names:
            return "unknown"
        
        # Count naming styles
        snake = sum(1 for n in names if '_' in n and n.islower())
        camel = sum(1 for n in names if n[0].islower() and any(c.isupper() for c in n))
        pascal = sum(1 for n in names if n[0].isupper() and any(c.islower() for c in n))
        
        if snake > camel and snake > pascal:
            return "snake_case"
        if camel > snake and camel > pascal:
            return "camelCase"
        if pascal > snake and pascal > camel:
            return "PascalCase"
        
        return "mixed"
    
    def _detect_indentation(self, files: List[Path]) -> tuple:
        """Detect indentation style and size."""
        indent_counts = Counter()
        
        for file_path in files[:20]:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                for line in content.split('\n'):
                    if line.startswith('\t'):
                        indent_counts['tabs'] += 1
                    elif line.startswith('    '):
                        indent_counts['4spaces'] += 1
                    elif line.startswith('  '):
                        indent_counts['2spaces'] += 1
            except Exception:
                continue
        
        if not indent_counts:
            return "spaces", 4
        
        most_common = indent_counts.most_common(1)[0][0]
        
        if most_common == 'tabs':
            return "tabs", 1
        elif most_common == '2spaces':
            return "spaces", 2
        else:
            return "spaces", 4
    
    def _detect_line_length(self, files: List[Path]) -> int:
        """Detect typical max line length."""
        max_lengths = []
        
        for file_path in files[:20]:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                lines = content.split('\n')
                if lines:
                    file_max = max(len(line) for line in lines if len(line) < 200)
                    max_lengths.append(file_max)
            except Exception:
                continue
        
        if not max_lengths:
            return 100
        
        # 90th percentile
        max_lengths.sort()
        idx = int(len(max_lengths) * 0.9)
        return max_lengths[idx] if idx < len(max_lengths) else 100
    
    def _detect_error_style(self, files: List[Path]) -> tuple:
        """Detect error handling style."""
        patterns = self.config.get("error_patterns", [])
        counts = Counter()
        wraps = False
        
        for file_path in files[:30]:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                for pattern, name in patterns:
                    if re.search(pattern, content):
                        counts[name] += 1
                        if "wrap" in name.lower():
                            wraps = True
            except Exception:
                continue
        
        if not counts:
            return "unknown", False
        
        most_common = counts.most_common(1)[0][0]
        return most_common, wraps
    
    def _detect_logging(self, files: List[Path]) -> tuple:
        """Detect logging library and format."""
        patterns = self.config.get("logging_patterns", [])
        counts = Counter()
        
        for file_path in files[:30]:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                for pattern, name in patterns:
                    if re.search(pattern, content):
                        counts[name] += 1
            except Exception:
                continue
        
        if not counts:
            return "unknown", "unknown"
        
        library = counts.most_common(1)[0][0]
        
        # Determine format
        structured = {"zerolog", "zap", "structlog", "pino", "winston"}
        log_format = "structured" if library in structured else "printf"
        
        return library, log_format
    
    def _detect_testing(self, files: List[Path]) -> tuple:
        """Detect testing framework and naming convention."""
        patterns = self.config.get("test_patterns", [])
        counts = Counter()
        
        # Look specifically in test files
        test_files = [f for f in files if "test" in f.name.lower()]
        
        for file_path in test_files[:20]:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                for pattern, name in patterns:
                    if re.search(pattern, content):
                        counts[name] += 1
            except Exception:
                continue
        
        if not counts:
            return "unknown", "test_"
        
        framework = counts.most_common(1)[0][0]
        
        # Detect naming
        if self.language == "python":
            naming = "test_"
        elif self.language == "go":
            naming = "Test"
        else:
            naming = "test_"
        
        return framework, naming
    
    def _collect_examples(self, files: List[Path]) -> Dict[str, List[str]]:
        """Collect representative code examples."""
        examples = {
            "error_handling": [],
            "function_signature": [],
            "logging": [],
        }
        
        for file_path in files[:10]:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                lines = content.split('\n')
                
                for i, line in enumerate(lines):
                    # Error handling examples
                    if self.language == "go" and "err != nil" in line:
                        snippet = '\n'.join(lines[max(0, i-1):min(len(lines), i+4)])
                        if len(snippet) < 200:
                            examples["error_handling"].append(snippet)
                    
                    # Function signature examples
                    if self.language == "python" and line.strip().startswith("def "):
                        examples["function_signature"].append(line.strip())
                    elif self.language == "go" and line.strip().startswith("func "):
                        examples["function_signature"].append(line.strip())
                    
                    # Logging examples
                    if "log." in line.lower() or "logger." in line.lower():
                        if len(line.strip()) < 100:
                            examples["logging"].append(line.strip())
            except Exception:
                continue
        
        # Limit examples
        for key in examples:
            examples[key] = examples[key][:3]
        
        return examples


# Convenience function
def analyze_project_style(repo_path: str, language: str) -> StyleFingerprint:
    """Quick way to get a project's style fingerprint."""
    analyzer = StyleAnalyzer(repo_path, language)
    return analyzer.analyze()
