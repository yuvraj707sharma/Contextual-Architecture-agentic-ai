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
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .logger import get_logger
from .tool_runtime import TOOL_SCHEMAS, ToolRuntime

logger = get_logger("thinking_agent")
console = Console()


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

        console.print(f"\n  [bold cyan]🤖 {self.name} Agent[/] thinking...\n")

        for step in range(self.max_steps):
            self.step_count = step + 1

            # Call LLM with tools
            try:
                response = await self._call_llm()
            except Exception as e:
                error_msg = f"LLM error at step {step + 1}: {type(e).__name__}: {e}"
                logger.error(error_msg, extra={"agent": self.name})
                console.print(f"  [red]❌ {error_msg}[/]")
                return f"Agent error: {error_msg}"

            # Check if model wants to call tools
            if response.get("tool_calls"):
                tool_calls = response["tool_calls"]
                for call in tool_calls:
                    tool_name = call.get("name", "unknown")
                    arguments = call.get("arguments", {})
                    call_id = call.get("id", "")

                    # Display tool call
                    self._display_tool_call(tool_name, arguments)

                    # Execute tool
                    result = await self.tool_runtime.execute(tool_name, arguments)

                    # Display result summary
                    self._display_tool_result(tool_name, result)

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

            console.print(
                f"\n  [dim]✅ {self.name} completed in {elapsed:.1f}s "
                f"({self.step_count} steps)[/]\n"
            )

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

    def _display_tool_call(self, tool_name: str, arguments: Dict[str, Any]):
        """Show a tool call in the terminal."""
        # Format arguments nicely
        arg_str = ""
        for key, val in arguments.items():
            val_str = str(val)
            if len(val_str) > 80:
                val_str = val_str[:77] + "..."
            arg_str += f" {key}={val_str}"

        console.print(f"    ├ [dim]🔧 {tool_name}[/]{arg_str}")

    def _display_tool_result(self, tool_name: str, result: str):
        """Show a tool result summary in the terminal."""
        # Show first line or character count
        lines = result.strip().splitlines()
        if not lines:
            summary = "(empty)"
        elif len(lines) == 1:
            summary = lines[0][:100]
        else:
            summary = f"{lines[0][:60]}... ({len(lines)} lines)"

        if result.startswith("Error"):
            console.print(f"    │   [red]{summary}[/]")
        else:
            console.print(f"    │   [dim]{summary}[/]")

    def _display_report(self, report: str):
        """Display the final report in a rich panel."""
        # Truncate for display — full version is in the saved file
        display_lines = report.splitlines()
        if len(display_lines) > 60:
            display_text = "\n".join(display_lines[:55])
            display_text += f"\n\n... ({len(display_lines) - 55} more lines in saved report)"
        else:
            display_text = report

        width = min(console.width, 90)
        report_text = Text(display_text)

        console.print(Panel(
            report_text,
            title=f"[bold cyan]{self.name} Report[/]",
            border_style="cyan",
            box=box.ROUNDED,
            width=width,
            padding=(1, 2),
        ))

    # ── Helpers ───────────────────────────────────────────

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
