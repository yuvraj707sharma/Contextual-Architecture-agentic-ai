"""Tests for the Skills system (agents.skills)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.skills import Skill, SkillManager, _compute_relevance, _tokenize

# ── Helpers ──────────────────────────────────────────────


def _make_skill(**overrides) -> Skill:
    """Factory for creating test skills with sensible defaults."""
    defaults = dict(
        name="add-jwt-middleware",
        description="Add JWT authentication middleware to a web API",
        trigger_keywords=["jwt", "auth", "middleware", "authentication", "token"],
        language="python",
        plan_template="# Steps\n1. Create middleware\n2. Add tests",
        file_patterns=["**/middleware/*.py", "**/auth/*.py"],
        test_strategy="Unit test with mock JWT tokens",
        success_count=3,
        fail_count=0,
        source_request="Add JWT authentication middleware",
        tags=["auth", "security", "web"],
    )
    defaults.update(overrides)
    return Skill(**defaults)


def _make_manager(tmp_path: Path) -> SkillManager:
    """Create a SkillManager pointing at tmp dirs."""
    global_dir = tmp_path / "global_skills"
    repo_dir = tmp_path / "repo_skills"
    return SkillManager(global_dir=global_dir, repo_dir=repo_dir)


# ── Skill dataclass ─────────────────────────────────────


class TestSkillDataclass:
    def test_default_timestamps(self):
        s = _make_skill()
        assert s.created_at  # auto-populated
        assert s.updated_at

    def test_success_rate_with_counts(self):
        s = _make_skill(success_count=7, fail_count=3)
        assert s.success_rate == pytest.approx(0.7)

    def test_success_rate_untested(self):
        s = _make_skill(success_count=0, fail_count=0)
        assert s.success_rate == pytest.approx(0.5)

    def test_success_rate_all_failures(self):
        s = _make_skill(success_count=0, fail_count=5)
        assert s.success_rate == pytest.approx(0.0)

    def test_to_dict_and_from_dict_roundtrip(self):
        original = _make_skill()
        data = original.to_dict()
        restored = Skill.from_dict(data)
        assert restored.name == original.name
        assert restored.trigger_keywords == original.trigger_keywords
        assert restored.success_count == original.success_count
        assert restored.tags == original.tags
        assert restored.plan_template == original.plan_template

    def test_from_dict_ignores_extra_keys(self):
        data = _make_skill().to_dict()
        data["unknown_field"] = "surprise"
        skill = Skill.from_dict(data)
        assert skill.name == "add-jwt-middleware"

    def test_from_dict_with_minimal_keys(self):
        data = {
            "name": "minimal",
            "description": "A minimal skill",
            "trigger_keywords": ["test"],
            "language": "python",
            "plan_template": "# Minimal",
            "file_patterns": [],
            "test_strategy": "none",
        }
        skill = Skill.from_dict(data)
        assert skill.name == "minimal"
        assert skill.success_count == 0
        assert skill.version == 1


# ── Tokenizer ────────────────────────────────────────────


class TestTokenize:
    def test_basic(self):
        tokens = _tokenize("Add JWT authentication middleware")
        assert "add" in tokens
        assert "jwt" in tokens
        assert "authentication" in tokens
        assert "middleware" in tokens

    def test_stop_words_removed(self):
        tokens = _tokenize("add a test for the module")
        assert "a" not in tokens
        assert "the" not in tokens
        assert "for" not in tokens

    def test_single_chars_removed(self):
        tokens = _tokenize("I want x y z tokens")
        assert "x" not in tokens
        assert "y" not in tokens
        assert "z" not in tokens

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_special_chars(self):
        tokens = _tokenize("hello-world foo_bar baz.qux")
        assert "hello" in tokens
        assert "world" in tokens
        assert "foo" in tokens
        assert "bar" in tokens


# ── Relevance scoring ───────────────────────────────────


class TestComputeRelevance:
    def test_exact_keyword_match(self):
        skill = _make_skill()
        score = _compute_relevance(["jwt", "auth"], skill)
        assert score > 0

    def test_no_match(self):
        skill = _make_skill()
        score = _compute_relevance(["graphql", "database", "migration"], skill)
        assert score == pytest.approx(0.0)

    def test_empty_query(self):
        skill = _make_skill()
        assert _compute_relevance([], skill) == 0.0

    def test_description_match_weaker_than_keyword(self):
        skill = _make_skill()
        kw_score = _compute_relevance(["jwt"], skill)  # in trigger_keywords
        # Create a skill where the word only appears in description
        skill2 = _make_skill(
            trigger_keywords=["unrelated"],
            tags=[],
            name="unrelated-skill",
            description="jwt support for web api",
        )
        desc_score = _compute_relevance(["jwt"], skill2)
        assert kw_score > desc_score

    def test_success_rate_boosts_score(self):
        good = _make_skill(success_count=10, fail_count=0)
        bad = _make_skill(success_count=0, fail_count=10)
        good_score = _compute_relevance(["jwt"], good)
        bad_score = _compute_relevance(["jwt"], bad)
        assert good_score > bad_score


# ── Save & Load round-trip ───────────────────────────────


class TestSaveLoad:
    def test_save_creates_file(self, tmp_path):
        mgr = _make_manager(tmp_path)
        skill = _make_skill()
        path = mgr.save(skill)
        assert path.exists()
        assert path.suffix == ".json"
        assert path.stem.endswith(".skill")

    def test_save_and_load_roundtrip(self, tmp_path):
        mgr = _make_manager(tmp_path)
        original = _make_skill()
        path = mgr.save(original)

        loaded = mgr._load_file(path)
        assert loaded is not None
        assert loaded.name == original.name
        assert loaded.trigger_keywords == original.trigger_keywords
        assert loaded.success_count == original.success_count
        assert loaded.plan_template == original.plan_template

    def test_save_repo_local(self, tmp_path):
        mgr = _make_manager(tmp_path)
        skill = _make_skill()
        path = mgr.save(skill, repo_local=True)
        assert "repo_skills" in str(path)

    def test_load_corrupt_file(self, tmp_path):
        mgr = _make_manager(tmp_path)
        bad_dir = tmp_path / "global_skills"
        bad_dir.mkdir(parents=True, exist_ok=True)
        bad_file = bad_dir / "corrupt.skill.json"
        bad_file.write_text("NOT VALID JSON {{{", encoding="utf-8")
        result = mgr._load_file(bad_file)
        assert result is None

    def test_load_empty_json(self, tmp_path):
        mgr = _make_manager(tmp_path)
        bad_dir = tmp_path / "global_skills"
        bad_dir.mkdir(parents=True, exist_ok=True)
        bad_file = bad_dir / "empty.skill.json"
        bad_file.write_text("{}", encoding="utf-8")
        # Missing required fields should fail
        result = mgr._load_file(bad_file)
        assert result is None

    def test_skill_filename_sanitisation(self):
        assert SkillManager._skill_filename("Add JWT Auth!") == "add-jwt-auth.skill.json"
        assert SkillManager._skill_filename("  hello  ") == "hello.skill.json"
        assert SkillManager._skill_filename("a--b") == "a-b.skill.json"


# ── list_all ─────────────────────────────────────────────


class TestListAll:
    def test_empty_dirs(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.list_all() == []

    def test_global_only(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="skill-a"))
        mgr.save(_make_skill(name="skill-b"))
        skills = mgr.list_all()
        assert len(skills) == 2
        assert skills[0].name == "skill-a"
        assert skills[1].name == "skill-b"

    def test_repo_overrides_global(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="shared", description="global version"))
        mgr.save(
            _make_skill(name="shared", description="repo version"),
            repo_local=True,
        )
        skills = mgr.list_all()
        assert len(skills) == 1
        assert skills[0].description == "repo version"

    def test_combined(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="global-only"))
        mgr.save(_make_skill(name="repo-only"), repo_local=True)
        skills = mgr.list_all()
        assert len(skills) == 2
        names = {s.name for s in skills}
        assert names == {"global-only", "repo-only"}

    def test_no_repo_dir(self, tmp_path):
        mgr = SkillManager(global_dir=tmp_path / "global_skills", repo_dir=None)
        mgr.save(_make_skill(name="alpha"))
        skills = mgr.list_all()
        assert len(skills) == 1


# ── find ─────────────────────────────────────────────────


class TestFind:
    def test_exact_match(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="jwt-auth", trigger_keywords=["jwt", "auth"]))
        mgr.save(_make_skill(name="db-migration", trigger_keywords=["database", "migration"],
                             description="Run database migrations", tags=["db"]))
        results = mgr.find("add jwt authentication")
        assert len(results) >= 1
        assert results[0].name == "jwt-auth"

    def test_language_filter(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="py-jwt", language="python",
                             trigger_keywords=["jwt"]))
        mgr.save(_make_skill(name="go-jwt", language="go",
                             trigger_keywords=["jwt"]))
        results = mgr.find("jwt auth", language="python")
        assert len(results) == 1
        assert results[0].name == "py-jwt"

    def test_no_match(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="jwt-auth", trigger_keywords=["jwt", "auth"]))
        results = mgr.find("kubernetes deployment helm chart")
        assert len(results) == 0

    def test_top_k_limit(self, tmp_path):
        mgr = _make_manager(tmp_path)
        for i in range(10):
            mgr.save(_make_skill(
                name=f"auth-variant-{i}",
                trigger_keywords=["auth", "middleware"],
            ))
        results = mgr.find("auth middleware", top_k=3)
        assert len(results) <= 3

    def test_empty_query(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill())
        assert mgr.find("") == []

    def test_find_prefers_higher_success_rate(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="jwt-good", trigger_keywords=["jwt"],
                             success_count=10, fail_count=0))
        mgr.save(_make_skill(name="jwt-bad", trigger_keywords=["jwt"],
                             success_count=0, fail_count=10))
        results = mgr.find("jwt")
        assert results[0].name == "jwt-good"


# ── get ──────────────────────────────────────────────────


class TestGet:
    def test_get_existing(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="my-skill"))
        assert mgr.get("my-skill") is not None

    def test_get_nonexistent(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.get("no-such-skill") is None

    def test_get_repo_overrides_global(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="dup", description="global"))
        mgr.save(_make_skill(name="dup", description="repo"), repo_local=True)
        skill = mgr.get("dup")
        assert skill is not None
        assert skill.description == "repo"


# ── record_outcome ───────────────────────────────────────


class TestRecordOutcome:
    def test_record_success(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="tracked", success_count=0, fail_count=0))
        mgr.record_outcome("tracked", success=True)
        reloaded = mgr.get("tracked")
        assert reloaded is not None
        assert reloaded.success_count == 1
        assert reloaded.fail_count == 0

    def test_record_failure(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="tracked", success_count=5, fail_count=2))
        mgr.record_outcome("tracked", success=False)
        reloaded = mgr.get("tracked")
        assert reloaded is not None
        assert reloaded.success_count == 5
        assert reloaded.fail_count == 3

    def test_record_multiple(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="multi", success_count=0, fail_count=0))
        for _ in range(5):
            mgr.record_outcome("multi", success=True)
        mgr.record_outcome("multi", success=False)
        reloaded = mgr.get("multi")
        assert reloaded is not None
        assert reloaded.success_count == 5
        assert reloaded.fail_count == 1

    def test_record_nonexistent_is_noop(self, tmp_path):
        mgr = _make_manager(tmp_path)
        # Should not raise
        mgr.record_outcome("does-not-exist", success=True)

    def test_record_on_repo_local_skill(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="repo-skill", success_count=0), repo_local=True)
        mgr.record_outcome("repo-skill", success=True)
        reloaded = mgr.get("repo-skill")
        assert reloaded is not None
        assert reloaded.success_count == 1


# ── create_from_run ──────────────────────────────────────


class TestCreateFromRun:
    def test_basic_creation(self, tmp_path):
        mgr = _make_manager(tmp_path)
        skill = mgr.create_from_run(
            user_request="Add rate limiting to the API",
            plan_data={
                "name": "add-rate-limiting",
                "description": "Add rate limiting middleware",
                "steps": ["Create limiter", "Register middleware", "Add tests"],
                "test_strategy": "Load test with concurrent requests",
                "tags": ["api", "security"],
            },
            language="python",
            file_patterns=["**/middleware/*.py"],
        )
        assert skill.name == "add-rate-limiting"
        assert "rate" in skill.trigger_keywords or "limiting" in skill.trigger_keywords
        assert skill.language == "python"
        assert "Create limiter" in skill.plan_template
        assert skill.tags == ["api", "security"]
        assert skill.source_request == "Add rate limiting to the API"
        assert skill.success_count == 0

    def test_auto_name_from_request(self, tmp_path):
        mgr = _make_manager(tmp_path)
        skill = mgr.create_from_run(
            user_request="Add logging to all endpoints",
            plan_data={
                "description": "Instrument endpoints with structured logging",
                "steps": ["Add logger", "Wrap handlers"],
            },
            language="python",
            file_patterns=["**/handlers/*.py"],
        )
        # Name should be auto-derived from request
        assert skill.name  # non-empty
        assert " " not in skill.name  # slug-ified

    def test_empty_steps(self, tmp_path):
        mgr = _make_manager(tmp_path)
        skill = mgr.create_from_run(
            user_request="Do something",
            plan_data={"name": "empty-steps"},
            language="go",
            file_patterns=[],
        )
        assert "no steps provided" in skill.plan_template

    def test_create_then_save_roundtrip(self, tmp_path):
        mgr = _make_manager(tmp_path)
        skill = mgr.create_from_run(
            user_request="Add caching layer",
            plan_data={
                "name": "add-cache",
                "description": "Redis caching layer",
                "steps": ["Add redis client", "Cache decorator"],
                "tags": ["cache", "redis"],
            },
            language="python",
            file_patterns=["**/cache/*.py"],
        )
        path = mgr.save(skill)
        loaded = mgr._load_file(path)
        assert loaded is not None
        assert loaded.name == "add-cache"
        assert loaded.source_request == "Add caching layer"


# ── apply_to_context ─────────────────────────────────────


class TestApplyToContext:
    def test_injects_all_fields(self):
        skill = _make_skill()
        ctx: dict = {"existing_key": "value"}
        result = SkillManager.apply_to_context(skill, ctx)

        assert result is ctx  # modified in-place
        assert ctx["skill_plan_template"] == skill.plan_template
        assert ctx["skill_name"] == skill.name
        assert ctx["skill_file_patterns"] == skill.file_patterns
        assert ctx["skill_test_strategy"] == skill.test_strategy
        assert ctx["skill_language"] == skill.language
        assert ctx["skill_description"] == skill.description
        assert ctx["skill_success_rate"] == skill.success_rate
        assert ctx["existing_key"] == "value"  # preserved

    def test_empty_context(self):
        skill = _make_skill()
        ctx: dict = {}
        SkillManager.apply_to_context(skill, ctx)
        assert "skill_name" in ctx

    def test_overwrites_previous_skill(self):
        skill1 = _make_skill(name="first")
        skill2 = _make_skill(name="second")
        ctx: dict = {}
        SkillManager.apply_to_context(skill1, ctx)
        assert ctx["skill_name"] == "first"
        SkillManager.apply_to_context(skill2, ctx)
        assert ctx["skill_name"] == "second"


# ── Edge cases ───────────────────────────────────────────


class TestEdgeCases:
    def test_duplicate_skill_names_overwrite(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.save(_make_skill(name="dup", description="v1"))
        mgr.save(_make_skill(name="dup", description="v2"))
        skills = mgr.list_all()
        assert len(skills) == 1
        assert skills[0].description == "v2"

    def test_skill_with_unicode(self, tmp_path):
        mgr = _make_manager(tmp_path)
        skill = _make_skill(name="unicode-test", description="Ünïcödé tëst 🚀")
        path = mgr.save(skill)
        loaded = mgr._load_file(path)
        assert loaded is not None
        assert loaded.description == "Ünïcödé tëst 🚀"

    def test_very_long_name(self, tmp_path):
        mgr = _make_manager(tmp_path)
        name = "a" * 200
        skill = _make_skill(name=name)
        path = mgr.save(skill)
        assert path.exists()
        # Filename stem should be truncated to ≤ 100 chars + ".skill.json"
        stem = path.stem  # e.g. "aaaa...aaa.skill"
        assert len(stem) <= 100 + len(".skill")
        loaded = mgr._load_file(path)
        assert loaded is not None
        # But the *data* inside preserves the full name
        assert loaded.name == name

    def test_nonexistent_directory_for_load(self, tmp_path):
        mgr = SkillManager(
            global_dir=tmp_path / "does_not_exist",
            repo_dir=tmp_path / "also_not_exist",
        )
        assert mgr.list_all() == []

    def test_concurrent_save_same_name(self, tmp_path):
        """Two saves to the same name should not corrupt the file."""
        mgr = _make_manager(tmp_path)
        for i in range(10):
            mgr.save(_make_skill(name="concurrent", success_count=i))
        loaded = mgr.get("concurrent")
        assert loaded is not None
        assert loaded.success_count == 9

    def test_json_file_is_valid(self, tmp_path):
        mgr = _make_manager(tmp_path)
        path = mgr.save(_make_skill())
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "name" in data
        assert "trigger_keywords" in data
