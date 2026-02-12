"""
Configuration - Centralized settings for the agent framework.

All hardcoded values converge here. Load from:
1. Defaults (sane zero-config)
2. Environment variables (12-factor style)
3. Config file (YAML or TOML, optional)
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


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
        from dataclasses import asdict
        d = asdict(self)
        if d.get("llm_api_key"):
            d["llm_api_key"] = d["llm_api_key"][:4] + "****"
        return d


def _parse_bool(value: str) -> bool:
    """Parse a boolean from an env var string."""
    return value.lower() in ("true", "1", "yes", "on")
