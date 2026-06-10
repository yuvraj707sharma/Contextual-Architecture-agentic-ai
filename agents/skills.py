"""
Skills — Procedural memory for the MACRO pipeline.

Skills are reusable plan templates that MACRO creates from successful runs.
Each skill is stored as a `.skill.json` file and can be discovered via
keyword matching against the user's request.

Storage locations:
  - Global:  ~/.contextual-architect/skills/
  - Repo:    <repo>/.contextual-architect/skills/
"""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .logger import get_logger

logger = get_logger("skills")

# ── Skill dataclass ──────────────────────────────────────


@dataclass
class Skill:
    """A reusable plan template extracted from a successful pipeline run."""

    name: str                       # e.g., "add-jwt-middleware"
    description: str                # What this skill does
    trigger_keywords: List[str]     # Keywords that activate this skill
    language: str                   # Target language
    plan_template: str              # The reusable plan markdown
    file_patterns: List[str]        # Globs of files typically modified
    test_strategy: str              # How to test this kind of change
    success_count: int = 0          # Times used successfully
    fail_count: int = 0             # Times it failed
    created_at: str = ""            # ISO timestamp
    updated_at: str = ""            # ISO timestamp
    source_request: str = ""        # Original user request that created it
    tags: List[str] = field(default_factory=list)
    version: int = 1

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    @property
    def success_rate(self) -> float:
        """Return a success-rate score in [0, 1], biased towards 0.5 when untested."""
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.5
        return self.success_count / total

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Skill:
        """Deserialize from a dictionary, tolerating missing/extra keys."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


# ── Keyword matching helpers ─────────────────────────────

_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "this", "that", "be", "as",
    "are", "was", "were", "been", "do", "does", "did", "will", "would",
    "should", "can", "could", "may", "might", "i", "we", "you", "my",
})

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    """Lowercase, split on non-alphanumeric, drop stop-words."""
    return [
        tok for tok in _TOKEN_RE.findall(text.lower())
        if tok not in _STOP_WORDS and len(tok) > 1
    ]


def _compute_relevance(query_tokens: List[str], skill: Skill) -> float:
    """
    Score a skill against query tokens using weighted field matching.

    Fields and their weights:
      - trigger_keywords: 3.0  (strongest signal)
      - name:             2.0
      - tags:             2.0
      - description:      1.0

    Each matching token contributes its field weight scaled by an IDF-like
    factor (shorter keywords are penalised less).  The raw score is then
    boosted by the skill's success rate.
    """
    if not query_tokens:
        return 0.0

    # Build per-field token sets
    kw_tokens = set()
    for kw in skill.trigger_keywords:
        kw_tokens.update(_tokenize(kw))

    name_tokens = set(_tokenize(skill.name))
    tag_tokens = set()
    for tag in skill.tags:
        tag_tokens.update(_tokenize(tag))
    desc_tokens = set(_tokenize(skill.description))

    score = 0.0
    query_set = set(query_tokens)

    for qt in query_set:
        # Exact matches
        if qt in kw_tokens:
            score += 3.0
        if qt in name_tokens:
            score += 2.0
        if qt in tag_tokens:
            score += 2.0
        if qt in desc_tokens:
            score += 1.0

        # Partial / substring matches (weaker)
        for kw_tok in kw_tokens:
            if qt != kw_tok and (qt in kw_tok or kw_tok in qt):
                score += 1.0
                break  # only once per query token
        for desc_tok in desc_tokens:
            if qt != desc_tok and (qt in desc_tok or desc_tok in qt):
                score += 0.3
                break

    # Normalise by query length so longer queries don't automatically outscore
    score /= len(query_set)

    # Boost by success rate  (range 0.5 – 1.0 for untested → perfect)
    boost = 0.5 + 0.5 * skill.success_rate
    score *= boost

    return score


# ── SkillManager ─────────────────────────────────────────


class SkillManager:
    """
    Manages MACRO's procedural memory — skills stored as `.skill.json` files.

    Two search paths are supported:
      * **global_dir** — user-wide skills in ``~/.contextual-architect/skills/``
      * **repo_dir** — repository-local skills in ``<repo>/.contextual-architect/skills/``

    Repository-local skills override global ones when names collide.
    """

    def __init__(
        self,
        global_dir: Optional[Path | str] = None,
        repo_dir: Optional[Path | str] = None,
    ) -> None:
        if global_dir is None:
            global_dir = Path.home() / ".contextual-architect" / "skills"
        self._global_dir = Path(global_dir)

        self._repo_dir: Optional[Path] = None
        if repo_dir is not None:
            self._repo_dir = Path(repo_dir)

    # ── persistence ──────────────────────────────────────

    @staticmethod
    def _skill_filename(name: str) -> str:
        """Convert a skill name to a safe filename (max 100-char stem)."""
        safe = re.sub(r"[^a-z0-9_-]", "-", name.lower().strip())
        safe = re.sub(r"-+", "-", safe).strip("-")
        # Truncate to avoid OS path-length limits (Windows MAX_PATH)
        if len(safe) > 100:
            safe = safe[:100].rstrip("-")
        return f"{safe}.skill.json"

    def save(self, skill: Skill, repo_local: bool = False) -> Path:
        """
        Persist a skill to disk as a ``.skill.json`` file.

        Args:
            skill: The skill to save.
            repo_local: If True, save to the repo directory instead of global.

        Returns:
            The path to the written file.
        """
        skill.updated_at = datetime.now(timezone.utc).isoformat()
        target_dir = self._repo_dir if (repo_local and self._repo_dir) else self._global_dir

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Failed to create skills directory %s: %s", target_dir, exc)
            raise

        path = target_dir / self._skill_filename(skill.name)
        try:
            path.write_text(
                json.dumps(skill.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("Saved skill '%s' → %s", skill.name, path)
        except OSError as exc:
            logger.error("Failed to write skill file %s: %s", path, exc)
            raise

        return path

    def _load_file(self, path: Path) -> Optional[Skill]:
        """Load a single skill from a JSON file, returning None on error."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Skill.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning("Corrupt skill file %s: %s", path, exc)
            return None
        except OSError as exc:
            logger.warning("Cannot read skill file %s: %s", path, exc)
            return None

    def _load_dir(self, directory: Path) -> Dict[str, Skill]:
        """Load all skills from a directory, keyed by name."""
        skills: Dict[str, Skill] = {}
        if not directory.is_dir():
            return skills
        for path in sorted(directory.glob("*.skill.json")):
            skill = self._load_file(path)
            if skill is not None:
                skills[skill.name] = skill
        return skills

    # ── queries ──────────────────────────────────────────

    def list_all(self) -> List[Skill]:
        """
        List every available skill (global + repo-local).

        Repo-local skills override global skills with the same name.

        Returns:
            A list of all skills, sorted by name.
        """
        combined: Dict[str, Skill] = {}
        combined.update(self._load_dir(self._global_dir))
        if self._repo_dir:
            combined.update(self._load_dir(self._repo_dir))
        return sorted(combined.values(), key=lambda s: s.name)

    def find(
        self,
        query: str,
        language: Optional[str] = None,
        top_k: int = 3,
    ) -> List[Skill]:
        """
        Find skills matching a natural-language query.

        Args:
            query: Free-text query (e.g. "add JWT auth middleware").
            language: If given, only return skills for this language.
            top_k: Maximum number of results.

        Returns:
            Top-k skills ranked by relevance × success rate, descending.
        """
        all_skills = self.list_all()
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scored: List[Tuple[float, Skill]] = []
        for skill in all_skills:
            if language and skill.language.lower() != language.lower():
                continue
            relevance = _compute_relevance(query_tokens, skill)
            if relevance > 0:
                scored.append((relevance, skill))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [skill for _, skill in scored[:top_k]]

    def get(self, skill_name: str) -> Optional[Skill]:
        """
        Retrieve a single skill by exact name.

        Repo-local takes precedence over global.

        Returns:
            The Skill if found, else None.
        """
        # Check repo-local first
        if self._repo_dir:
            path = self._repo_dir / self._skill_filename(skill_name)
            if path.exists():
                return self._load_file(path)

        path = self._global_dir / self._skill_filename(skill_name)
        if path.exists():
            return self._load_file(path)
        return None

    # ── outcome tracking ─────────────────────────────────

    def record_outcome(self, skill_name: str, success: bool) -> None:
        """
        Record whether a skill's application succeeded or failed.

        Increments ``success_count`` or ``fail_count`` and persists the change.
        Searches repo-local first, then global.

        Args:
            skill_name: The name of the skill.
            success: True if the run succeeded.
        """
        # Determine which directory the skill lives in
        skill: Optional[Skill] = None
        repo_local = False

        if self._repo_dir:
            path = self._repo_dir / self._skill_filename(skill_name)
            if path.exists():
                skill = self._load_file(path)
                repo_local = True

        if skill is None:
            path = self._global_dir / self._skill_filename(skill_name)
            if path.exists():
                skill = self._load_file(path)

        if skill is None:
            logger.warning("Cannot record outcome: skill '%s' not found", skill_name)
            return

        if success:
            skill.success_count += 1
        else:
            skill.fail_count += 1

        self.save(skill, repo_local=repo_local)
        logger.info(
            "Recorded %s for skill '%s' (success=%d, fail=%d)",
            "success" if success else "failure",
            skill_name,
            skill.success_count,
            skill.fail_count,
        )

    # ── skill creation ───────────────────────────────────

    def create_from_run(
        self,
        user_request: str,
        plan_data: Dict[str, Any],
        language: str,
        file_patterns: List[str],
    ) -> Skill:
        """
        Auto-extract a skill from a successful pipeline run.

        Args:
            user_request: The original user request.
            plan_data: Dict with keys like ``name``, ``description``,
                ``steps`` (list of step strings), ``test_strategy``, ``tags``.
            language: Target programming language.
            file_patterns: Glob patterns of files typically touched.

        Returns:
            A newly created (but not yet saved) Skill.
        """
        # Derive a slug name from the plan or request
        raw_name = plan_data.get("name", "")
        if not raw_name:
            raw_name = re.sub(r"[^a-z0-9 ]", "", user_request.lower())
            raw_name = "-".join(raw_name.split()[:6])

        # Build the plan template markdown
        steps = plan_data.get("steps", [])
        steps_md = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) if steps else "1. (no steps provided)"

        files_md = "\n".join(f"- `{p}`" for p in file_patterns) if file_patterns else "- (none)"

        plan_template = (
            f"# Plan Template\n\n"
            f"## Steps\n{steps_md}\n\n"
            f"## Target Files\n{files_md}\n"
        )

        # Extract trigger keywords from the request + description
        description = plan_data.get("description", user_request)
        combined_text = f"{user_request} {description}"
        keywords = list(dict.fromkeys(_tokenize(combined_text)))[:15]

        tags = plan_data.get("tags", [])
        test_strategy = plan_data.get(
            "test_strategy",
            f"Unit tests for {language} code changes",
        )

        return Skill(
            name=raw_name,
            description=description,
            trigger_keywords=keywords,
            language=language,
            plan_template=plan_template,
            file_patterns=file_patterns,
            test_strategy=test_strategy,
            source_request=user_request,
            tags=tags if isinstance(tags, list) else [tags],
        )

    # ── context injection ────────────────────────────────

    @staticmethod
    def apply_to_context(skill: Skill, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inject a skill's plan template and metadata into a planner context.

        The context dict is updated **in-place** and also returned.

        Args:
            skill: The skill to inject.
            context: The mutable pipeline context dictionary.

        Returns:
            The modified context with skill data injected.
        """
        context["skill_plan_template"] = skill.plan_template
        context["skill_name"] = skill.name
        context["skill_file_patterns"] = skill.file_patterns
        context["skill_test_strategy"] = skill.test_strategy
        context["skill_language"] = skill.language
        context["skill_description"] = skill.description
        context["skill_success_rate"] = skill.success_rate
        return context
