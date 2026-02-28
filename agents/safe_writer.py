"""
Safe Writer - Permission-based code modification system.

This is the LAST layer before any code touches the filesystem.
NOTHING bypasses this module.

Core Principles:
1. New files: Create freely (safe)
2. Existing files: Show diff, ask permission
3. Never delete or rewrite without explicit approval
4. Always create backups before modifying
"""

import os
import shutil
import difflib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional


class ChangeType(Enum):
    """Types of changes the system can propose."""
    CREATE_FILE = "create"       # New file — safe
    ADD_LINES = "add"            # Adding lines to existing file
    MODIFY_LINES = "modify"      # Changing existing lines — DANGEROUS
    DELETE_LINES = "delete"      # Removing lines — VERY DANGEROUS
    DELETE_FILE = "delete_file"  # Deleting entire file — CRITICAL
    ADD_DEPENDENCY = "dependency"  # Adding to go.mod/requirements.txt


class RiskLevel(Enum):
    """Risk level of a proposed change."""
    SAFE = "safe"                # New file, no existing code affected
    LOW = "low"                  # Adding lines, no existing code changed
    MEDIUM = "medium"            # Modifying a few lines
    HIGH = "high"                # Modifying many lines or core files
    CRITICAL = "critical"        # Deleting code or modifying DB/config


@dataclass
class ProposedChange:
    """A single proposed change to the codebase."""
    
    file_path: str
    change_type: ChangeType
    risk_level: RiskLevel
    
    # What the user sees
    description: str
    
    # The actual changes
    new_content: Optional[str] = None      # For CREATE_FILE
    diff_lines: List[str] = field(default_factory=list)  # Unified diff
    
    # Statistics
    lines_added: int = 0
    lines_removed: int = 0
    
    # Permission tracking
    approved: Optional[bool] = None        # None = not yet asked
    auto_approved: bool = False            # True for new files
    
    # Context for the user
    reason: str = ""                       # Why this change is needed
    
    def to_display_string(self) -> str:
        """Generate human-readable change description."""
        lines = []
        
        icon = {
            ChangeType.CREATE_FILE: "📁",
            ChangeType.ADD_LINES: "➕",
            ChangeType.MODIFY_LINES: "📝",
            ChangeType.DELETE_LINES: "🗑️",
            ChangeType.DELETE_FILE: "⛔",
            ChangeType.ADD_DEPENDENCY: "📦",
        }.get(self.change_type, "📄")
        
        risk_icon = {
            RiskLevel.SAFE: "✅",
            RiskLevel.LOW: "🟢",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.HIGH: "🟠",
            RiskLevel.CRITICAL: "🔴",
        }.get(self.risk_level, "⚪")
        
        lines.append(f"{icon} {self.change_type.value.upper()}: {self.file_path}")
        lines.append(f"   Risk: {risk_icon} {self.risk_level.value}")
        lines.append(f"   {self.description}")
        
        if self.lines_added > 0 or self.lines_removed > 0:
            lines.append(f"   +{self.lines_added} / -{self.lines_removed} lines")
        
        if self.change_type == ChangeType.CREATE_FILE and self.new_content:
            # Show preview of new file
            preview_lines = self.new_content.split('\n')[:10]
            lines.append("")
            for pl in preview_lines:
                lines.append(f"   + {pl}")
            if len(self.new_content.split('\n')) > 10:
                remaining = len(self.new_content.split('\n')) - 10
                lines.append(f"   ... ({remaining} more lines)")
        
        elif self.diff_lines:
            # Show diff preview
            lines.append("")
            for dl in self.diff_lines[:15]:
                lines.append(f"   {dl}")
            if len(self.diff_lines) > 15:
                lines.append(f"   ... ({len(self.diff_lines) - 15} more lines)")
        
        return '\n'.join(lines)


@dataclass
class ChangeSet:
    """A complete set of proposed changes."""
    
    changes: List[ProposedChange] = field(default_factory=list)
    untouched_files: List[str] = field(default_factory=list)
    
    @property
    def needs_permission(self) -> bool:
        """Check if any change requires user permission."""
        return any(
            not c.auto_approved and c.approved is None
            for c in self.changes
        )
    
    @property
    def safe_changes(self) -> List[ProposedChange]:
        """Changes that don't need permission (new files)."""
        return [c for c in self.changes if c.auto_approved]
    
    @property
    def permission_required(self) -> List[ProposedChange]:
        """Changes that need explicit user approval."""
        return [c for c in self.changes if not c.auto_approved]
    
    @property
    def all_approved(self) -> bool:
        """Check if all changes have been approved."""
        return all(
            c.approved is True or c.auto_approved
            for c in self.changes
        )
    
    def approve_all(self):
        """Approve all pending changes."""
        for change in self.changes:
            if change.approved is None:
                change.approved = True
    
    def approve_by_index(self, indices: List[int]):
        """Approve specific changes by index."""
        for idx in indices:
            if 0 <= idx < len(self.changes):
                self.changes[idx].approved = True
    
    def reject_by_index(self, indices: List[int]):
        """Reject specific changes by index."""
        for idx in indices:
            if 0 <= idx < len(self.changes):
                self.changes[idx].approved = False
    
    def to_user_prompt(self) -> str:
        """Generate the full permission prompt for the user."""
        sections = []
        
        # Section 1: Safe changes (auto-approved)
        safe = self.safe_changes
        if safe:
            sections.append("═" * 60)
            sections.append("✅ NEW FILES (auto-approved)")
            sections.append("═" * 60)
            for change in safe:
                sections.append(change.to_display_string())
                sections.append("")
        
        # Section 2: Changes needing permission
        needs_approval = self.permission_required
        if needs_approval:
            sections.append("═" * 60)
            sections.append("⚠️  MODIFICATIONS (permission required)")
            sections.append("═" * 60)
            for i, change in enumerate(needs_approval):
                sections.append(f"\n[{i}] {change.to_display_string()}")
        
        # Section 3: Explicitly NOT touched
        if self.untouched_files:
            sections.append("")
            sections.append("═" * 60)
            sections.append("🚫 NOT MODIFIED (preserved as-is)")
            sections.append("═" * 60)
            for f in self.untouched_files[:15]:
                sections.append(f"   → {f}")
            if len(self.untouched_files) > 15:
                sections.append(f"   ... and {len(self.untouched_files) - 15} more files")
        
        # Summary
        total = len(self.changes)
        safe_count = len(safe)
        modify_count = len(needs_approval)
        
        sections.append("")
        sections.append("═" * 60)
        sections.append(f"SUMMARY: {total} changes ({safe_count} auto-approved, {modify_count} need permission)")
        sections.append("═" * 60)
        
        return '\n'.join(sections)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_changes": len(self.changes),
            "auto_approved": len(self.safe_changes),
            "needs_permission": len(self.permission_required),
            "untouched_count": len(self.untouched_files),
            "changes": [
                {
                    "file": c.file_path,
                    "type": c.change_type.value,
                    "risk": c.risk_level.value,
                    "description": c.description,
                    "approved": c.approved,
                    "auto_approved": c.auto_approved,
                }
                for c in self.changes
            ],
        }


class SafeCodeWriter:
    """
    The safety layer between generated code and the filesystem.
    
    NOTHING gets written to disk without going through this class.
    This is the last line of defense against AI destroying code.
    """
    
    # Files that are EXTRA dangerous to modify
    CRITICAL_FILES = {
        "go.mod", "go.sum",
        "package.json", "package-lock.json", "yarn.lock",
        "requirements.txt", "pyproject.toml", "poetry.lock",
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".env", ".env.production", ".env.local",
        "Makefile",
        "main.go", "main.py", "index.ts", "index.js", "app.py",
        "settings.py", "config.py", "config.go",
    }
    
    # Patterns that should NEVER be auto-approved
    DANGEROUS_PATTERNS = [
        "DROP TABLE", "DELETE FROM", "TRUNCATE",
        "os.Remove", "os.RemoveAll",
        "shutil.rmtree", "shutil.remove",
        "rm -rf", "rm -f",
        "FORMAT", "DESTROY",
        "exec(", "eval(",
        "__import__",
    ]
    
    def __init__(self, project_path: str, backup_dir: Optional[str] = None):
        self.project_path = Path(project_path)
        self.backup_dir = Path(backup_dir) if backup_dir else self.project_path / ".ai_backups"
    
    def plan_changes(
        self,
        generated_files: Dict[str, str],
        language: str = "python",
    ) -> ChangeSet:
        """
        Analyze generated code and create a safe change plan.
        
        This does NOT write anything. It only PLANS what to write
        and categorizes each change by risk level.
        
        Args:
            generated_files: Dict of {relative_path: content}
            language: Programming language
        
        Returns:
            ChangeSet with all proposed changes
        """
        changeset = ChangeSet()
        touched_files = set()
        
        for file_path, new_content in generated_files.items():
            full_path = self.project_path / file_path
            touched_files.add(file_path)
            
            if not full_path.exists():
                # NEW FILE — safe to create
                change = self._plan_new_file(file_path, new_content)
                changeset.changes.append(change)
            else:
                # EXISTING FILE — requires permission
                change = self._plan_modification(file_path, full_path, new_content)
                if change:
                    changeset.changes.append(change)
        
        # Track which files we are NOT touching
        all_code_files = self._find_all_code_files(language)
        changeset.untouched_files = sorted(
            [f for f in all_code_files if f not in touched_files]
        )
        
        return changeset
    
    def _plan_new_file(self, file_path: str, content: str) -> ProposedChange:
        """Plan creation of a new file."""
        # Check for dangerous patterns even in new files
        risk = RiskLevel.SAFE
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in content.lower():
                risk = RiskLevel.HIGH
                break
        
        # Check if it's a critical file type
        if Path(file_path).name in self.CRITICAL_FILES:
            risk = RiskLevel.MEDIUM
        
        line_count = len(content.split('\n'))
        
        return ProposedChange(
            file_path=file_path,
            change_type=ChangeType.CREATE_FILE,
            risk_level=risk,
            description=f"New file ({line_count} lines)",
            new_content=content,
            lines_added=line_count,
            lines_removed=0,
            auto_approved=(risk == RiskLevel.SAFE),
            reason="New functionality requested by user",
        )
    
    def _plan_modification(
        self,
        file_path: str,
        full_path: Path,
        new_content: str
    ) -> Optional[ProposedChange]:
        """Plan modifications to an existing file."""
        try:
            existing_content = full_path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return None
        
        # Generate unified diff
        existing_lines = existing_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = list(difflib.unified_diff(
            existing_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm='',
        ))
        
        if not diff:
            return None  # No changes needed
        
        # Count additions and deletions
        additions = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
        deletions = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))
        
        # ── GUARDRAIL: Block destructive modifications ──────────
        # If the generated code would delete >50% of an existing file,
        # this is almost certainly wrong (e.g., Implementer replacing
        # entire file instead of modifying it). Block it.
        if len(existing_lines) > 10 and deletions > len(existing_lines) * 0.5:
            return ProposedChange(
                file_path=file_path,
                change_type=ChangeType.MODIFY_LINES,
                risk_level=RiskLevel.CRITICAL,
                description=(
                    f"⛔ BLOCKED: Would delete {deletions}/{len(existing_lines)} lines "
                    f"({int(deletions/len(existing_lines)*100)}% of file). "
                    f"This looks like a full replacement, not a modification. "
                    f"Consider creating a new file instead."
                ),
                new_content=new_content,
                diff_lines=diff,
                lines_added=additions,
                lines_removed=deletions,
                auto_approved=False,
                approved=False,  # Pre-rejected
                reason="Destructive modification blocked by safety guard",
            )
        
        # Determine change type
        if deletions == 0:
            change_type = ChangeType.ADD_LINES
        elif additions == 0:
            change_type = ChangeType.DELETE_LINES
        else:
            change_type = ChangeType.MODIFY_LINES
        
        # Determine risk level
        risk = self._calculate_risk(file_path, additions, deletions, len(existing_lines), new_content)
        
        return ProposedChange(
            file_path=file_path,
            change_type=change_type,
            risk_level=risk,
            description=f"Modify existing file",
            new_content=new_content,
            diff_lines=diff,
            lines_added=additions,
            lines_removed=deletions,
            auto_approved=False,  # NEVER auto-approve modifications
            reason="Required for requested feature",
        )
    
    def _calculate_risk(
        self,
        file_path: str,
        additions: int,
        deletions: int,
        total_existing: int,
        new_content: str,
    ) -> RiskLevel:
        """Calculate the risk level of a modification."""
        file_name = Path(file_path).name
        
        # Critical files always need extra scrutiny
        if file_name in self.CRITICAL_FILES:
            return RiskLevel.CRITICAL
        
        # Check for dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in new_content.lower():
                return RiskLevel.CRITICAL
        
        # Deleting more than 30% of a file is HIGH risk
        if total_existing > 0 and deletions > total_existing * 0.3:
            return RiskLevel.HIGH
        
        # Deleting more than 10 lines is MEDIUM risk
        if deletions > 10:
            return RiskLevel.MEDIUM
        
        # Any deletion is at least LOW risk
        if deletions > 0:
            return RiskLevel.LOW
        
        # Adding a few lines is LOW
        if additions < 20:
            return RiskLevel.LOW
        
        return RiskLevel.MEDIUM
    
    def apply_changes(self, changeset: ChangeSet) -> Dict[str, Any]:
        """
        Apply ONLY the approved changes.
        
        Creates backups before modifying existing files.
        
        Returns:
            Report of what was written and what was skipped
        """
        applied = []
        skipped = []
        backed_up = []
        errors = []
        
        # Create backup directory if needed
        if any(c.change_type != ChangeType.CREATE_FILE for c in changeset.changes if c.approved):
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        for change in changeset.changes:
            if not (change.approved or change.auto_approved):
                skipped.append(change.file_path)
                continue
            
            full_path = self.project_path / change.file_path
            
            try:
                if change.change_type == ChangeType.CREATE_FILE:
                    # Create new file
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(change.new_content, encoding='utf-8')
                    applied.append(change.file_path)
                
                else:
                    # Modification - backup first
                    if full_path.exists():
                        backup_name = f"{full_path.name}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                        backup_path = self.backup_dir / backup_name
                        shutil.copy2(full_path, backup_path)
                        backed_up.append(str(backup_path))
                    
                    # Write new content
                    full_path.write_text(change.new_content, encoding='utf-8')
                    applied.append(change.file_path)
            
            except Exception as e:
                errors.append(f"{change.file_path}: {str(e)}")
        
        return {
            "applied": applied,
            "skipped": skipped,
            "backed_up": backed_up,
            "errors": errors,
            "total_applied": len(applied),
            "total_skipped": len(skipped),
            "success": len(errors) == 0,
        }
    
    def restore_backup(self, backup_path: str) -> bool:
        """Restore a file from backup."""
        backup = Path(backup_path)
        if not backup.exists():
            return False
        
        # Extract original filename (remove timestamp and .bak)
        # Format: filename.ext.20240601_120000.bak
        parts = backup.name.rsplit('.', 2)
        if len(parts) >= 3:
            original_name = parts[0] + '.' + parts[1].split('.')[0]
        else:
            original_name = parts[0]
        
        # Find the original file (this is a heuristic)
        # In practice, you'd want to store the mapping
        original_path = self.project_path / original_name
        
        shutil.copy2(backup, original_path)
        return True
    
    def _find_all_code_files(self, language: str) -> List[str]:
        """Find all code files in the project."""
        extensions = {
            "go": [".go"],
            "python": [".py"],
            "typescript": [".ts", ".tsx"],
            "javascript": [".js", ".jsx"],
            "cpp": [".cpp", ".cc", ".cxx", ".h", ".hpp"],
            "c": [".c", ".h"],
            "java": [".java"],
        }
        exts = extensions.get(language, [])
        files = []
        
        ignore_dirs = {
            '.git', 'vendor', 'node_modules', '__pycache__',
            '.venv', 'venv', 'dist', 'build', '.next', '.ai_backups'
        }
        
        for root, dirs, filenames in os.walk(self.project_path):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            
            for fname in filenames:
                if any(fname.endswith(ext) for ext in exts):
                    rel_path = os.path.relpath(
                        os.path.join(root, fname),
                        self.project_path,
                    )
                    files.append(rel_path)
        
        return files


# Convenience functions
def plan_safe_changes(
    project_path: str,
    files: Dict[str, str],
    language: str = "python"
) -> ChangeSet:
    """Quick way to plan changes."""
    writer = SafeCodeWriter(project_path)
    return writer.plan_changes(files, language)


def apply_safe_changes(
    project_path: str,
    changeset: ChangeSet
) -> Dict[str, Any]:
    """Quick way to apply approved changes."""
    writer = SafeCodeWriter(project_path)
    return writer.apply_changes(changeset)
