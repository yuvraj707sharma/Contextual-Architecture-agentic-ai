"""
Configuration - Centralized settings for the agent framework.

All hardcoded values converge here. Load from:
1. Defaults (sane zero-config)
2. Environment variables (12-factor style)
3. Config file (YAML or TOML, optional)
"""

import os
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from pathlib import Path


@dataclass
class AgentConfig:
    """
    Central configuration for the entire agent pipeline.

    Usage:
        config = AgentConfig()                 # defaults
        config = AgentConfig.from_env()        # env vars
        config = AgentConfig.from_file("config.yaml")  # file
    """

    # ── LLM ──────────────────────────────────────────────
    llm_provider: str = "mock"  # deepseek, ollama, openai, anthropic, mock
    llm_model: Optional[str] = None  # None → provider default
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096
    llm_api_key: Optional[str] = None  # override env var

    # ── Per-Agent Provider Routing ────────────────────────
    # If set, these override llm_provider for specific agents.
    # Smart agents (planner, implementer) can use a better model.
    planner_provider: Optional[str] = None
    planner_api_key: Optional[str] = None
    implementer_provider: Optional[str] = None
    implementer_api_key: Optional[str] = None

    # ── Pipeline ─────────────────────────────────────────
    max_retries: int = 3
    auto_approve_new_files: bool = True

    # ── Reviewer ─────────────────────────────────────────
    use_external_tools: bool = True
    reviewer_timeout: int = 30  # seconds per external tool

    # ── Scanning limits ──────────────────────────────────
    max_files_to_scan: int = 100
    max_files_per_extension: int = 20
    max_line_length: int = 120

    # ── Logging ──────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "pretty"  # "pretty" (emoji + color) or "json"

    # ── Paths ────────────────────────────────────────────
    backup_dir: Optional[str] = None  # None → .ai_backups in project
    default_language: str = "python"

    # ── .macro.yaml overrides ─────────────────────────────
    # These can be set per-project via .macro.yaml
    security_cwe_denylist: list = field(default_factory=list)  # e.g., ["CWE-78", "CWE-89"]
    security_require_reviewer: bool = True
    ignore_patterns: list = field(default_factory=list)  # e.g., ["migrations/", "generated/"]
    style_naming: Optional[str] = None  # e.g., "snake_case"
    style_max_line_length: Optional[int] = None
    style_logging: Optional[str] = None  # e.g., "structlog"

    @classmethod
    def from_project_yaml(cls, repo_path: str) -> "AgentConfig":
        """Load config from .macro.yaml in the project root.
        
        This is a per-project config that teams check into git.
        It layers on top of the user config (env vars still override).
        
        .macro.yaml format:
            language: python
            test_runner: pytest
            style:
              naming: snake_case
              max_line_length: 100
              logging: structlog
            agents:
              fast_provider: groq
              smart_provider: google
            security:
              cwe_denylist: [CWE-78, CWE-89, CWE-502]
              require_reviewer: true
            ignore:
              - "migrations/"
              - "generated/"
        """
        import importlib
        
        yaml_path = Path(repo_path) / ".macro.yaml"
        if not yaml_path.exists():
            yaml_path = Path(repo_path) / ".macro.yml"
        if not yaml_path.exists():
            return cls()  # No project config, return defaults
        
        try:
            yaml = importlib.import_module("yaml")
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except ImportError:
            # YAML not installed, try JSON fallback
            data = json.loads(yaml_path.read_text(encoding="utf-8"))
        
        if not isinstance(data, dict):
            return cls()
        
        kwargs: Dict[str, Any] = {}
        
        # Top-level fields
        if "language" in data:
            kwargs["default_language"] = data["language"]
        if "test_runner" in data:
            pass  # Scanner detects this; log for reference
        if "max_retries" in data:
            kwargs["max_retries"] = int(data["max_retries"])
        
        # Style section
        style = data.get("style", {})
        if isinstance(style, dict):
            if "naming" in style:
                kwargs["style_naming"] = style["naming"]
            if "max_line_length" in style:
                kwargs["style_max_line_length"] = int(style["max_line_length"])
                kwargs["max_line_length"] = int(style["max_line_length"])
            if "logging" in style:
                kwargs["style_logging"] = style["logging"]
        
        # Agents section (provider routing)
        agents = data.get("agents", {})
        if isinstance(agents, dict):
            if "fast_provider" in agents:
                kwargs["llm_provider"] = agents["fast_provider"]
            if "smart_provider" in agents:
                kwargs["planner_provider"] = agents["smart_provider"]
                kwargs["implementer_provider"] = agents["smart_provider"]
        
        # Security section
        security = data.get("security", {})
        if isinstance(security, dict):
            if "cwe_denylist" in security:
                kwargs["security_cwe_denylist"] = list(security["cwe_denylist"])
            if "require_reviewer" in security:
                kwargs["security_require_reviewer"] = bool(security["require_reviewer"])
        
        # Ignore patterns
        ignore = data.get("ignore", [])
        if isinstance(ignore, list):
            kwargs["ignore_patterns"] = ignore
        
        # Logging
        if "log_level" in data:
            kwargs["log_level"] = data["log_level"]
        if "log_format" in data:
            kwargs["log_format"] = data["log_format"]
        
        return cls(**kwargs)

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Load config from environment variables.

        Env var naming: ``CA_<FIELD_NAME>`` in uppercase.
        Example: ``CA_LLM_PROVIDER=deepseek``
        """
        kwargs: Dict[str, Any] = {}

        env_map = {
            "CA_LLM_PROVIDER": ("llm_provider", str),
            "CA_LLM_MODEL": ("llm_model", str),
            "CA_LLM_TEMPERATURE": ("llm_temperature", float),
            "CA_LLM_MAX_TOKENS": ("llm_max_tokens", int),
            "CA_LLM_API_KEY": ("llm_api_key", str),
            "CA_MAX_RETRIES": ("max_retries", int),
            "CA_AUTO_APPROVE_NEW_FILES": ("auto_approve_new_files", _parse_bool),
            "CA_USE_EXTERNAL_TOOLS": ("use_external_tools", _parse_bool),
            "CA_REVIEWER_TIMEOUT": ("reviewer_timeout", int),
            "CA_MAX_FILES_TO_SCAN": ("max_files_to_scan", int),
            "CA_MAX_LINE_LENGTH": ("max_line_length", int),
            "CA_LOG_LEVEL": ("log_level", str),
            "CA_LOG_FORMAT": ("log_format", str),
            "CA_BACKUP_DIR": ("backup_dir", str),
        }

        for env_key, (field_name, converter) in env_map.items():
            value = os.environ.get(env_key)
            if value is not None:
                try:
                    kwargs[field_name] = converter(value)
                except (ValueError, TypeError):
                    pass  # skip malformed env vars

        # Auto-detect provider + key from environment
        if "llm_provider" not in kwargs or "llm_api_key" not in kwargs:
            from .llm_client import detect_provider_from_env
            detected_provider, detected_key = detect_provider_from_env()
            
            if "llm_provider" not in kwargs and detected_provider != "mock":
                kwargs["llm_provider"] = detected_provider
            
            if "llm_api_key" not in kwargs and detected_key:
                kwargs["llm_api_key"] = detected_key

        return cls(**kwargs)

    @classmethod
    def from_file(cls, path: str) -> "AgentConfig":
        """Load config from a YAML file.

        Args:
            path: Path to the YAML config file.
        """
        import importlib

        file_path = os.path.abspath(path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Config file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Try YAML first, fall back to JSON
        try:
            yaml = importlib.import_module("yaml")
            data = yaml.safe_load(content)
        except ImportError:
            import json
            data = json.loads(content)

        if not isinstance(data, dict):
            raise ValueError(f"Config file must be a mapping, got {type(data).__name__}")

        # Only keep keys that match dataclass fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}

        return cls(**filtered)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize config to a dictionary (safe for logging — masks API key)."""
        d = asdict(self)
        for key in ("llm_api_key", "planner_api_key", "implementer_api_key"):
            if d.get(key):
                d[key] = d[key][:4] + "****"
        return d

    @staticmethod
    def config_dir() -> Path:
        """Get the user config directory (~/.contextual-architect/)."""
        config_home = Path.home() / ".contextual-architect"
        config_home.mkdir(parents=True, exist_ok=True)
        return config_home

    def save_to_file(self, path: Optional[str] = None):
        """Save config to JSON for reuse.
        
        API keys are saved in plaintext but the file is protected
        with owner-only permissions (chmod 0o600 on Unix).
        For display/logging, use to_dict() which masks keys.
        """
        if path is None:
            path = str(self.config_dir() / "config.json")
        data = asdict(self)
        # Don't save None values
        data = {k: v for k, v in data.items() if v is not None}
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        # SECURITY: Set file permissions to owner-only (VULN-6)
        try:
            if os.name != 'nt':  # Unix/Mac
                os.chmod(path, 0o600)
            else:
                # Windows: no chmod equivalent without win32security
                import warnings
                warnings.warn(
                    f"Config file contains API keys in plaintext: {path}\n"
                    f"On Windows, ensure only your user account has access to this file.",
                    UserWarning,
                    stacklevel=2,
                )
        except OSError:
            pass  # Best effort
        
        return path

    @classmethod
    def load_user_config(cls) -> "AgentConfig":
        """Load config from user's home dir, then layer env vars on top."""
        config_path = cls.config_dir() / "config.json"
        if config_path.exists():
            try:
                base = cls.from_file(str(config_path))
            except Exception:
                base = cls()
        else:
            base = cls()
        
        # Layer env vars on top (only override if explicitly set)
        env_map = {
            "CA_LLM_PROVIDER": "llm_provider",
            "CA_LLM_MODEL": "llm_model",
            "CA_LLM_API_KEY": "llm_api_key",
            "CA_LLM_TEMPERATURE": "llm_temperature",
            "CA_LLM_MAX_TOKENS": "llm_max_tokens",
            "CA_MAX_RETRIES": "max_retries",
            "CA_AUTO_APPROVE_NEW_FILES": "auto_approve_new_files",
            "CA_USE_EXTERNAL_TOOLS": "use_external_tools",
            "CA_REVIEWER_TIMEOUT": "reviewer_timeout",
            "CA_MAX_FILES_TO_SCAN": "max_files_to_scan",
            "CA_MAX_LINE_LENGTH": "max_line_length",
            "CA_LOG_LEVEL": "log_level",
            "CA_LOG_FORMAT": "log_format",
            "CA_BACKUP_DIR": "backup_dir",
        }
        
        # Load env-based config to layer on top
        env_config = cls.from_env()
        
        # Only override fields where the env var is actually present
        for env_key, field_name in env_map.items():
            if os.environ.get(env_key) is not None:
                setattr(base, field_name, getattr(env_config, field_name))
        
        # Also layer provider-specific API keys from env
        provider_env_keys = [
            ("GROQ_API_KEY", "groq"),
            ("GOOGLE_API_KEY", "google"),
            ("GEMINI_API_KEY", "google"),
            ("OPENAI_API_KEY", "openai"),
            ("ANTHROPIC_API_KEY", "anthropic"),
            ("DEEPSEEK_API_KEY", "deepseek"),
        ]
        for env_key, provider in provider_env_keys:
            if os.environ.get(env_key):
                # If env has a provider key, override provider + key
                if not os.environ.get("CA_LLM_PROVIDER"):
                    base.llm_provider = env_config.llm_provider
                base.llm_api_key = env_config.llm_api_key
                break  # First found wins (same priority as detect_provider_from_env)
        
        return base


def _parse_bool(value: str) -> bool:
    """Parse a boolean from an env var string."""
    return value.lower() in ("true", "1", "yes", "on")
