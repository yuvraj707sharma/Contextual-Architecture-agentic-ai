"""
MACRO Plugin Interfaces — Inspired by ComposioHQ/agent-orchestrator.

Protocol-based interfaces that make MACRO extensible without forking.
Anyone can implement a plugin by conforming to the Protocol contract.

Usage:
    class MyCustomLLM:
        async def generate(self, system: str, user: str, **kwargs) -> str:
            return call_my_api(system, user)

        @property
        def model_name(self) -> str:
            return "my-custom-model"

    # Use it in MACRO — no subclassing needed, just Protocol conformance
    orchestrator = Orchestrator(llm_client=MyCustomLLM())
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# ── LLM Plugin ────────────────────────────────────────────

@runtime_checkable
class LLMPlugin(Protocol):
    """Any LLM provider must implement this interface.

    Built-in implementations: GroqClient, GeminiClient, OpenAIClient.
    To add a new provider:

        class AnthropicClient:
            async def generate(self, system, user, **kwargs) -> str:
                return await anthropic.messages.create(...)

            @property
            def model_name(self) -> str:
                return "claude-3-opus"
    """

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        **kwargs,
    ) -> Any:
        """Generate a response from the LLM.

        Returns an object with a `.content` attribute (str).
        """
        ...

    @property
    def model_name(self) -> str:
        """Return the model name (e.g., 'gemini-2.0-flash')."""
        ...


# ── Writer Plugin ─────────────────────────────────────────

@runtime_checkable
class WriterPlugin(Protocol):
    """Any file writer must implement this interface.

    Built-in implementation: SafeCodeWriter.
    Custom implementations could add:
    - Git commit after write
    - PR creation
    - Dry-run mode
    - Cloud storage sync
    """

    def plan_changes(
        self,
        generated_files: Dict[str, str],
        language: str,
    ) -> Any:
        """Plan file changes without writing yet.

        Returns a ChangeSet describing what will be written.
        """
        ...

    def apply_changes(
        self,
        changeset: Any,
        dry_run: bool = False,
    ) -> Dict[str, str]:
        """Apply the planned changes to disk.

        Returns dict of {file_path: status} (e.g., "created", "modified").
        """
        ...


# ── Reviewer Plugin ───────────────────────────────────────

@runtime_checkable
class ReviewerPlugin(Protocol):
    """Any code reviewer must implement this interface.

    Built-in implementation: ReviewerAgent (LLM-based).
    Custom implementations could add:
    - Static analysis (ruff, eslint)
    - Security scanning (bandit, semgrep)
    - Type checking (mypy, tsc)
    """

    async def review(
        self,
        code: str,
        file_path: str,
        language: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Review generated code.

        Returns an object with `.passed` (bool) and `.summary` (str).
        """
        ...


# ── Tracker Plugin ────────────────────────────────────────

@runtime_checkable
class TrackerPlugin(Protocol):
    """Any issue tracker (GitHub Issues, Linear, Jira, etc.).

    No built-in implementation yet. To add:

        class GitHubTracker:
            def __init__(self, repo, token):
                self.gh = github.Github(token)
                self.repo = self.gh.get_repo(repo)

            def get_issue(self, issue_id):
                issue = self.repo.get_issue(int(issue_id))
                return {"title": issue.title, "body": issue.body}

            def update_status(self, issue_id, status):
                issue = self.repo.get_issue(int(issue_id))
                issue.edit(state=status)

            def create_issue(self, title, body, labels=None):
                return self.repo.create_issue(title=title, body=body)
    """

    def get_issue(self, issue_id: str) -> Dict[str, Any]:
        """Fetch issue details."""
        ...

    def update_status(self, issue_id: str, status: str) -> None:
        """Update issue status (e.g., 'open' -> 'closed')."""
        ...

    def create_issue(
        self,
        title: str,
        body: str,
        labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a new issue. Returns issue details."""
        ...


# ── Scanner Plugin ────────────────────────────────────────

@runtime_checkable
class ScannerPlugin(Protocol):
    """Any project scanner must implement this interface.

    Built-in implementation: ProjectScanner.
    Custom implementations could add:
    - Cloud infrastructure scanning (Terraform, CDK)
    - Container image analysis
    - Secret detection
    """

    def scan(self) -> Any:
        """Scan the project and return a snapshot.

        Returns an object with `.to_dict()` and `.to_prompt_context()`.
        """
        ...


# ── Notifier Plugin ───────────────────────────────────────

@runtime_checkable
class NotifierPlugin(Protocol):
    """Any notification system (Slack, Discord, email, etc.).

    No built-in implementation yet. To add:

        class SlackNotifier:
            def __init__(self, webhook_url):
                self.webhook = webhook_url

            def notify(self, message, level="info"):
                requests.post(self.webhook, json={"text": message})
    """

    def notify(
        self,
        message: str,
        level: str = "info",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send a notification."""
        ...


# ── Plugin Registry ───────────────────────────────────────

class PluginRegistry:
    """Central registry for all MACRO plugins.

    Usage:
        registry = PluginRegistry()
        registry.register("llm", my_custom_llm)
        registry.register("tracker", my_jira_tracker)

        llm = registry.get("llm")
        tracker = registry.get("tracker")
    """

    # Map plugin names to their Protocol types for validation
    PLUGIN_TYPES = {
        "llm": LLMPlugin,
        "writer": WriterPlugin,
        "reviewer": ReviewerPlugin,
        "tracker": TrackerPlugin,
        "scanner": ScannerPlugin,
        "notifier": NotifierPlugin,
    }

    def __init__(self):
        self._plugins: Dict[str, Any] = {}

    def register(self, name: str, plugin: Any) -> None:
        """Register a plugin.

        Args:
            name: Plugin slot name (e.g., "llm", "tracker")
            plugin: Plugin instance conforming to the Protocol

        Raises:
            TypeError: If plugin doesn't match expected Protocol
            ValueError: If name is not a known plugin slot
        """
        if name not in self.PLUGIN_TYPES:
            raise ValueError(
                f"Unknown plugin slot '{name}'. "
                f"Available: {', '.join(self.PLUGIN_TYPES.keys())}"
            )

        expected_type = self.PLUGIN_TYPES[name]
        if not isinstance(plugin, expected_type):
            raise TypeError(
                f"Plugin for '{name}' does not conform to {expected_type.__name__} protocol. "
                f"Expected methods: {[m for m in dir(expected_type) if not m.startswith('_')]}"
            )

        self._plugins[name] = plugin

    def get(self, name: str, default: Any = None) -> Any:
        """Get a registered plugin by name."""
        return self._plugins.get(name, default)

    def has(self, name: str) -> bool:
        """Check if a plugin is registered."""
        return name in self._plugins

    def list_registered(self) -> List[str]:
        """List all registered plugin names."""
        return list(self._plugins.keys())

    def list_available(self) -> List[str]:
        """List all available plugin slots."""
        return list(self.PLUGIN_TYPES.keys())
