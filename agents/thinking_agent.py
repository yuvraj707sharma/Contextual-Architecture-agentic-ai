"""
Thinking Agent — The core agent loop for tool-calling models.

This is the heart of MACRO v2. A ThinkingAgent:
1. Receives a task from the user
2. Has a persona (system prompt) and tools
3. Calls the LLM with tools available
4. Executes tool calls, feeds results back
5. Repeats until the model produces a final answer
6. Displays results in chat + saves report to disk

Works with any LLM provider that supports tool/function calling:
- Google Gemini (native tool calling)
- Groq (native tool calling)
- OpenAI-compatible (DeepSeek, etc.)
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .logger import get_logger
from .tool_runtime import TOOL_SCHEMAS, ToolRuntime

logger = get_logger("thinking_agent")
console = Console()

# Status symbols inspired by Gemini CLI
STATUS_OK = "[green]✓[/]"
STATUS_EXEC = "[cyan]⊷[/]"
STATUS_ERR = "[red]✗[/]"
STATUS_WAIT = "[yellow]◦[/]"


class ThinkingAgent:
    """A thinking model with tools that explores and produces reports.

    The agent runs in a loop:
        User task → LLM (with tools) → tool calls → execute → feed back → repeat → final answer

    The loop continues until:
        - The model produces a text response (final answer)
        - Max steps reached (safety limit)

    All tool calls are displayed live in the terminal for transparency.
    """

    def __init__(
        self,
        name: str,
        persona: str,
        llm_client: Any,
        repo_path: str,
        tools: Optional[List[Dict]] = None,
        max_steps: int = 30,
    ):
        """Initialize a thinking agent.

        Args:
            name: Agent name (e.g., 'Explorer', 'Security')
            persona: System prompt defining the agent's role
            llm_client: Any LLM client with generate_with_tools()
            repo_path: Path to the repository to analyze
            tools: Tool schemas (defaults to all TOOL_SCHEMAS)
            max_steps: Max tool calls before stopping (safety)
        """
        self.name = name
        self.persona = persona
        self.llm = llm_client
        self.repo_path = repo_path
        self.tool_runtime = ToolRuntime(repo_path)
        self.tools = tools or TOOL_SCHEMAS
        self.max_steps = max_steps
        self.messages: List[Dict[str, Any]] = []
        self.step_count = 0
        self.total_tokens = 0
        self.tool_stats: Dict[str, Dict[str, Any]] = {}  # track per-tool stats

    async def run(self, task: str) -> str:
        """Run the agent loop until it produces a final answer.

        Args:
            task: The user's task/question for this agent

        Returns:
            The agent's final response (markdown text)
        """
        start_time = time.monotonic()

        # Initialize conversation
        self.messages = [
            {"role": "system", "content": self.persona},
            {"role": "user", "content": self._build_task_prompt(task)},
        ]
        self.step_count = 0

        console.print(f"\n  [bold cyan]◆ {self.name} Agent[/] [dim]analyzing...[/]\n")

        for step in range(self.max_steps):
            self.step_count = step + 1

            # Call LLM with tools (with rate-limit retry)
            response = None
            for attempt in range(4):  # up to 3 retries
                try:
                    response = await self._call_llm()
                    break
                except Exception as e:
                    err_str = str(e)
                    is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "rate" in err_str.lower()

                    if is_rate_limit and attempt < 3:
                        wait_secs = self._extract_retry_delay(err_str) or (3 * (2 ** attempt))
                        console.print(
                            f"    {STATUS_WAIT} [yellow]Rate limited "
                            f"— waiting {wait_secs:.0f}s[/] "
                            f"[dim]({attempt + 1}/3)[/]"
                        )
                        import asyncio
                        await asyncio.sleep(wait_secs)
                        continue
                    else:
                        clean_err = self._clean_error_message(e)
                        logger.error(clean_err, extra={"agent": self.name})
                        console.print(f"    {STATUS_ERR} [red]{clean_err}[/]")
                        return f"Agent error: {clean_err}"

            if response is None:
                return "Agent error: no response after retries"

            # Check if model wants to call tools
            if response.get("tool_calls"):
                tool_calls = response["tool_calls"]
                for call in tool_calls:
                    tool_name = call.get("name", "unknown")
                    arguments = call.get("arguments", {})
                    call_id = call.get("id", "")

                    # Display tool call (in-progress)
                    self._display_tool_call(tool_name, arguments, executing=True)

                    # Execute tool (timed)
                    t0 = time.monotonic()
                    result = await self.tool_runtime.execute(tool_name, arguments)
                    call_elapsed = time.monotonic() - t0

                    # Track per-tool stats
                    is_error = result.startswith("Error")
                    if tool_name not in self.tool_stats:
                        self.tool_stats[tool_name] = {
                            "calls": 0, "errors": 0, "total_ms": 0.0,
                        }
                    self.tool_stats[tool_name]["calls"] += 1
                    self.tool_stats[tool_name]["total_ms"] += call_elapsed * 1000
                    if is_error:
                        self.tool_stats[tool_name]["errors"] += 1

                    # Display result summary
                    self._display_tool_result(
                        tool_name, result, call_elapsed, is_error,
                    )

                    # Add to conversation
                    self.messages.append({
                        "role": "assistant",
                        "tool_calls": [call],
                    })
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": tool_name,
                        "content": result,
                    })
                continue

            # Model produced final answer
            final_answer = response.get("content", "")
            elapsed = time.monotonic() - start_time

            # Display session summary
            self._display_session_summary(elapsed)

            # Display the report
            self._display_report(final_answer)

            logger.info(
                f"{self.name} agent completed: {self.step_count} steps, "
                f"{elapsed:.1f}s",
                extra={"agent": self.name},
            )

            return final_answer

        # Safety limit reached
        elapsed = time.monotonic() - start_time
        msg = (
            f"{self.name} agent reached max steps ({self.max_steps}) "
            f"after {elapsed:.1f}s. Partial results may be available "
            f"in .contextual-architect/reports/"
        )
        console.print(f"\n  [yellow]⚠️ {msg}[/]")
        return msg

    # ── LLM Interaction ───────────────────────────────────

    async def _call_llm(self) -> Dict[str, Any]:
        """Call the LLM with current messages and tools.

        Returns dict with either 'content' (final answer) or 'tool_calls'.
        """
        # Use generate_with_tools if available, otherwise fall back
        if hasattr(self.llm, "generate_with_tools"):
            return await self.llm.generate_with_tools(
                messages=self.messages,
                tools=self.tools,
                temperature=0.1,
            )
        else:
            # Fallback: use regular generate with tool descriptions in prompt
            return await self._fallback_generate()

    async def _fallback_generate(self) -> Dict[str, Any]:
        """Fallback for LLMs without native tool calling.

        Embeds tool descriptions in the system prompt and parses
        JSON tool calls from the model's text output.
        """
        # Build a prompt that includes tool descriptions
        tool_desc = "You have these tools available:\n\n"
        for schema in self.tools:
            func = schema["function"]
            tool_desc += f"- **{func['name']}**: {func['description']}\n"
            params = func.get("parameters", {}).get("properties", {})
            if params:
                tool_desc += f"  Parameters: {json.dumps(params, indent=2)}\n"

        tool_desc += (
            "\n\nTo call a tool, respond ONLY with a JSON block:\n"
            '```json\n{"tool": "tool_name", "arguments": {...}}\n```\n\n'
            "When you are done analyzing, respond normally with your complete "
            "markdown report. Do NOT wrap your final report in JSON."
        )

        # Prepend tool descriptions to the system message
        messages_copy = list(self.messages)
        if messages_copy and messages_copy[0]["role"] == "system":
            messages_copy[0] = {
                "role": "system",
                "content": messages_copy[0]["content"] + "\n\n" + tool_desc,
            }

        # Build a single prompt from messages
        system = messages_copy[0]["content"] if messages_copy else ""
        user_parts = []
        for msg in messages_copy[1:]:
            role = msg["role"]
            content = msg.get("content", "")
            if role == "tool":
                user_parts.append(f"[Tool result for {msg.get('name', '?')}]:\n{content}")
            elif role == "assistant" and msg.get("tool_calls"):
                calls = msg["tool_calls"]
                for c in calls:
                    user_parts.append(
                        f"[You called {c.get('name', '?')} with: "
                        f"{json.dumps(c.get('arguments', {}))}]"
                    )
            elif content:
                user_parts.append(content)

        user_prompt = "\n\n".join(user_parts)

        response = await self.llm.generate(
            system_prompt=system,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=8192,
        )

        text = response.content if hasattr(response, "content") else str(response)

        # Try to parse tool calls from text
        tool_call = self._parse_tool_from_text(text)
        if tool_call:
            return {"tool_calls": [tool_call]}

        return {"content": text}

    @staticmethod
    def _parse_tool_from_text(text: str) -> Optional[Dict[str, Any]]:
        """Parse a JSON tool call from text output."""
        import re
        # Look for ```json blocks or raw JSON
        patterns = [
            r'```json\s*\n\s*(\{.*?\})\s*\n\s*```',  # ```json {...} ```
            r'(\{"tool"\s*:.*?\})',  # raw JSON with "tool" key
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    if "tool" in data:
                        return {
                            "id": f"fallback_{id(data)}",
                            "name": data["tool"],
                            "arguments": data.get("arguments", {}),
                        }
                except (json.JSONDecodeError, KeyError):
                    continue
        return None

    # ── Display Methods ───────────────────────────────────

    def _display_tool_call(
        self, tool_name: str, arguments: Dict[str, Any], executing: bool = False,
    ):
        """Show a tool call in the terminal with tree formatting."""
        # Format arguments concisely
        arg_parts = []
        for key, val in arguments.items():
            val_str = str(val)
            if len(val_str) > 60:
                val_str = val_str[:57] + "..."
            arg_parts.append(f"[dim]{key}=[/]{val_str}")
        args_display = " ".join(arg_parts)

        status = STATUS_EXEC if executing else STATUS_OK
        console.print(f"    ├─ {status} [bold]{tool_name}[/] {args_display}")

    def _display_tool_result(
        self, tool_name: str, result: str,
        elapsed: float = 0.0, is_error: bool = False,
    ):
        """Show a tool result summary with elapsed time."""
        lines = result.strip().splitlines()
        if not lines:
            summary = "(empty)"
        elif len(lines) == 1:
            summary = lines[0][:90]
        else:
            summary = f"{lines[0][:55]}... ({len(lines)} lines)"

        time_str = f"[dim]{elapsed:.1f}s[/]" if elapsed > 0.01 else ""

        if is_error:
            console.print(f"    │  {STATUS_ERR} [red]{summary}[/] {time_str}")
        else:
            console.print(f"    │  [dim]{summary}[/] {time_str}")

    def _display_session_summary(self, elapsed: float):
        """Show a clean session stats summary box."""
        unique_tools = len(self.tool_stats)
        total_calls = sum(s["calls"] for s in self.tool_stats.values())
        total_errors = sum(s["errors"] for s in self.tool_stats.values())

        # Build stats table
        table = Table(
            show_header=False, box=box.SIMPLE, padding=(0, 1),
            show_edge=False,
        )
        table.add_column(style="dim")
        table.add_column(style="bold")

        table.add_row("Steps", str(self.step_count))
        table.add_row("Time", f"{elapsed:.1f}s")
        table.add_row("Tool calls", f"{total_calls} ({unique_tools} unique)")
        if total_errors > 0:
            table.add_row("Errors", f"[red]{total_errors}[/]")

        # Tool breakdown
        if self.tool_stats:
            breakdown_parts = []
            for name, stats in sorted(
                self.tool_stats.items(),
                key=lambda x: x[1]["calls"],
                reverse=True,
            ):
                avg_ms = stats["total_ms"] / max(stats["calls"], 1)
                breakdown_parts.append(
                    f"{name} x{stats['calls']} [dim]({avg_ms:.0f}ms avg)[/]"
                )
            table.add_row("Tools", ", ".join(breakdown_parts[:4]))

        console.print()
        console.print(Panel(
            table,
            title=f"[bold green]✓[/] [bold]{self.name}[/] [dim]complete[/]",
            border_style="green",
            box=box.ROUNDED,
            padding=(0, 1),
            width=min(console.width, 80),
        ))

    def _display_report(self, report: str):
        """Display the final report in a rich panel."""
        display_lines = report.splitlines()
        if len(display_lines) > 50:
            display_text = "\n".join(display_lines[:45])
            remaining = len(display_lines) - 45
            display_text += f"\n\n[dim]... {remaining} more lines in saved report[/]"
        else:
            display_text = report

        width = min(console.width, 88)
        console.print(Panel(
            display_text,
            title=f"[bold cyan]{self.name} Report[/]",
            border_style="dim cyan",
            box=box.ROUNDED,
            width=width,
            padding=(1, 2),
        ))

    # ── Helpers ───────────────────────────────────────────

    @staticmethod
    def _clean_error_message(exc: Exception) -> str:
        """Extract a clean one-liner from API error blobs."""
        err = str(exc)
        # Extract 'message' from JSON-like error strings
        msg_match = re.search(r"'message':\s*'([^']+)'", err)
        if msg_match:
            msg = msg_match.group(1)
            # Trim at \n for readability
            msg = msg.split("\\n")[0].split("\n")[0]
            if len(msg) > 120:
                msg = msg[:117] + "..."
            return msg
        # Fallback: just the exception type + first 100 chars
        short = err[:100] + "..." if len(err) > 100 else err
        return f"{type(exc).__name__}: {short}"

    @staticmethod
    def _extract_retry_delay(err_str: str) -> Optional[float]:
        """Extract retry delay from a rate-limit error message."""
        match = re.search(r'retryDelay.*?(\d+\.?\d*)s', err_str)
        if match:
            return float(match.group(1)) + 1  # add 1s buffer
        match = re.search(r"retry in (\d+\.?\d*)s", err_str, re.IGNORECASE)
        if match:
            return float(match.group(1)) + 1
        return None

    def _build_task_prompt(self, task: str) -> str:
        """Build the initial task prompt with repo context."""
        repo_name = Path(self.repo_path).name
        return (
            f"## Task\n\n{task}\n\n"
            f"## Context\n\n"
            f"You are analyzing the repository: **{repo_name}**\n"
            f"Repository path: {self.repo_path}\n\n"
            f"Use your tools to explore the codebase. Start by listing "
            f"the root directory to understand the project structure, "
            f"then dive deeper into relevant files.\n\n"
            f"When you have completed your analysis, write your report "
            f"using the `write_report` tool, then provide a summary "
            f"as your final response."
        )
