"""
Tests for agent configuration and setup wizard logic.
"""

import os
import json
import tempfile
import pytest
from unittest.mock import patch

from ..config import AgentConfig
from ..setup_wizard import test_api_key as verify_api_key, get_preset_config


class TestAgentConfig:
    """Tests for AgentConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AgentConfig()
        assert config.llm_provider == "mock"
        assert config.planner_provider is None
        assert config.planner_model is None
        assert config.implementer_provider is None
        assert config.implementer_model is None

    def test_env_var_override(self):
        """Test environment variable overrides."""
        env_overrides = {
            "CA_LLM_PROVIDER": "anthropic",
            "CA_LLM_MODEL": "claude-3-5-haiku-20241022",
            "CA_PLANNER_PROVIDER": "anthropic",
            "CA_PLANNER_MODEL": "claude-4.5-sonnet",
            "CA_IMPLEMENTER_PROVIDER": "anthropic",
            "CA_IMPLEMENTER_MODEL": "claude-4.5-sonnet",
        }

        with patch.dict(os.environ, env_overrides):
            config = AgentConfig.from_env()
            assert config.llm_provider == "anthropic"
            assert config.llm_model == "claude-3-5-haiku-20241022"
            assert config.planner_provider == "anthropic"
            assert config.planner_model == "claude-4.5-sonnet"
            assert config.implementer_provider == "anthropic"
            assert config.implementer_model == "claude-4.5-sonnet"

    def test_save_and_load_config(self):
        """Test serializing to JSON and loading back."""
        config = AgentConfig(
            llm_provider="google",
            llm_model="gemini-2.5-flash",
            planner_provider="google",
            planner_model="gemini-2.5-pro",
            implementer_provider="google",
            implementer_model="gemini-2.5-pro",
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Save configuration
            config.save_to_file(tmp_path)

            # Load configuration back
            loaded = AgentConfig.from_file(tmp_path)
            assert loaded.llm_provider == "google"
            assert loaded.llm_model == "gemini-2.5-flash"
            assert loaded.planner_provider == "google"
            assert loaded.planner_model == "gemini-2.5-pro"
            assert loaded.implementer_provider == "google"
            assert loaded.implementer_model == "gemini-2.5-pro"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class TestSetupWizardHelpers:
    """Tests for setup wizard connection testing and helpers."""

    @patch("httpx.get")
    def test_ollama_connection_success(self, mock_get):
        """Test test_api_key detects Ollama running successfully."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"version": "0.1.48"}

        ok, msg = verify_api_key("ollama", None)
        assert ok is True
        assert "Ollama is running" in msg
        assert "v0.1.48" in msg

    @patch("httpx.get")
    def test_ollama_connection_failure(self, mock_get):
        """Test test_api_key handles Ollama connection failures gracefully."""
        mock_get.side_effect = Exception("Connection refused")

        ok, msg = verify_api_key("ollama", None)
        assert ok is False
        assert "Could not connect to Ollama" in msg

    def test_preset_config_mappings(self):
        """Test that get_preset_config returns the correct AgentConfig mappings."""
        # 1. Google Gemini Preset
        gemini = get_preset_config("1", "gemini_key")
        assert gemini["llm_provider"] == "google"
        assert gemini["llm_model"] == "gemini-2.5-flash"
        assert gemini["planner_model"] == "gemini-2.5-pro"
        assert gemini["llm_api_key"] == "gemini_key"
        assert gemini["planner_api_key"] == "gemini_key"

        # 2. Anthropic Claude Preset
        anthropic = get_preset_config("2", "ant_key")
        assert anthropic["llm_provider"] == "anthropic"
        assert anthropic["llm_model"] == "claude-3-5-haiku-20241022"
        assert anthropic["planner_model"] == "claude-4.5-sonnet"

        # 3. OpenAI Preset
        openai = get_preset_config("3", "oa_key")
        assert openai["llm_provider"] == "openai"
        assert openai["llm_model"] == "gpt-4o-mini"
        assert openai["planner_model"] == "gpt-4o"

        # 4. Multi-Provider Preset
        multi = get_preset_config("4", "groq_key", "gemini_key")
        assert multi["llm_provider"] == "groq"
        assert multi["llm_model"] == "llama-3.3-70b-versatile"
        assert multi["llm_api_key"] == "groq_key"
        assert multi["planner_provider"] == "google"
        assert multi["planner_model"] == "gemini-2.5-pro"
        assert multi["planner_api_key"] == "gemini_key"
