"""
Shared test fixtures for the agent test suite.
"""


import pytest

from ..base import AgentContext
from ..config import AgentConfig
from ..llm_client import MockLLMClient


@pytest.fixture
def tmp_repo(tmp_path):
    """
    A temporary repository with sample project files.

    Creates a realistic project layout for agents to scan.
    """
    # Create directory structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "utils").mkdir()
    (tmp_path / "tests").mkdir()

    # Python files with various styles
    (tmp_path / "src" / "main.py").write_text(
        '"""Main entry point."""\n\n'
        'import asyncio\n'
        'from src.utils.helpers import format_name\n\n\n'
        'def run_app():\n'
        '    """Start the application."""\n'
        '    print("Hello world")\n\n\n'
        'if __name__ == "__main__":\n'
        '    run_app()\n',
        encoding="utf-8",
    )

    (tmp_path / "src" / "utils" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "utils" / "helpers.py").write_text(
        '"""Utility helpers."""\n\n'
        'import re\n'
        'import logging\n\n'
        'logger = logging.getLogger(__name__)\n\n\n'
        'def format_name(name: str) -> str:\n'
        '    """Format a user name."""\n'
        '    return name.strip().title()\n\n\n'
        'def validate_email(email: str) -> bool:\n'
        '    """Check if email looks valid."""\n'
        '    pattern = r"^[\\w.-]+@[\\w.-]+\\.\\w+$"\n'
        '    return bool(re.match(pattern, email))\n',
        encoding="utf-8",
    )

    (tmp_path / "src" / "models.py").write_text(
        '"""Data models."""\n\n'
        'from dataclasses import dataclass\n'
        'from typing import Optional\n\n\n'
        '@dataclass\n'
        'class User:\n'
        '    """A user in the system."""\n'
        '    name: str\n'
        '    email: str\n'
        '    age: Optional[int] = None\n',
        encoding="utf-8",
    )

    (tmp_path / "tests" / "__init__.py").write_text("", encoding="utf-8")

    # Config files
    (tmp_path / "requirements.txt").write_text(
        "fastapi>=0.100\nhttpx>=0.24\npydantic>=2.0\n",
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture
def agent_context(tmp_repo):
    """An AgentContext pointing at the tmp_repo."""
    return AgentContext(
        user_request="Add user authentication",
        repo_path=str(tmp_repo),
        language="python",
    )


@pytest.fixture
def mock_llm():
    """A MockLLMClient with a default code response."""
    return MockLLMClient(responses=[
        '```python\ndef authenticate(token: str) -> bool:\n'
        '    """Validate a JWT token."""\n'
        '    # TODO: implement\n'
        '    return True\n```'
    ])


@pytest.fixture
def config():
    """Default test config with external tools disabled."""
    return AgentConfig(
        llm_provider="mock",
        use_external_tools=False,
        log_level="WARNING",
    )
