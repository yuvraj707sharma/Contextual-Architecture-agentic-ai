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
        
        SECURITY: API keys are masked before writing. Only the first
        and last 4 characters are stored — enough to identify which
        key is configured, not enough to use it. Keys should be set
        via environment variables (GROQ_API_KEY, GOOGLE_API_KEY, etc).
        """
        if path is None:
            path = str(self.config_dir() / "config.json")
        data = asdict(self)
        # Don't save None values
        data = {k: v for k, v in data.items() if v is not None}
        
        # SECURITY: Mask API keys before writing (VULN-2)
        for key_field in ("llm_api_key", "planner_api_key", "implementer_api_key"):
            if data.get(key_field) and len(data[key_field]) > 8:
                val = data[key_field]
                data[key_field] = val[:4] + "****" + val[-4:]
            elif data.get(key_field):
                data[key_field] = "****"
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        # SECURITY: Set file permissions to owner-only (VULN-6)
        try:
            if os.name != 'nt':  # Unix/Mac
                os.chmod(path, 0o600)
        except OSError:
            pass  # Best effort — some filesystems don't support chmod
        
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
        
        # Layer env vars on top
        env_config = cls.from_env()
        # Only override fields that were explicitly set in env
        for field_name in cls.__dataclass_fields__:
            env_val = getattr(env_config, field_name)
            default_val = cls.__dataclass_fields__[field_name].default
            if env_val != default_val:
                setattr(base, field_name, env_val)
        
        return base


def _parse_bool(value: str) -> bool:
    """Parse a boolean from an env var string."""
    return value.lower() in ("true", "1", "yes", "on")
