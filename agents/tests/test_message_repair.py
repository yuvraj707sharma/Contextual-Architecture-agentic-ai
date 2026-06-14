"""Tests for message sequence repair logic."""

import pytest

from agents.llm_client import _repair_message_sequence


def test_consecutive_user_messages_merged():
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "user", "content": "World"},
    ]
    repaired = _repair_message_sequence(messages)
    assert len(repaired) == 1
    assert repaired[0]["role"] == "user"
    assert repaired[0]["content"] == "Hello\n\nWorld"


def test_consecutive_assistant_messages_merged():
    messages = [
        {"role": "assistant", "content": "Thinking..."},
        {"role": "assistant", "content": "Done thinking."},
    ]
    repaired = _repair_message_sequence(messages)
    assert len(repaired) == 1
    assert repaired[0]["role"] == "assistant"
    assert repaired[0]["content"] == "Thinking...\n\nDone thinking."


def test_orphaned_tool_response_fixed():
    # A tool response without a preceding assistant tool call
    messages = [
        {"role": "tool", "name": "run_command", "tool_call_id": "call_123", "content": "Success"},
    ]
    repaired = _repair_message_sequence(messages)
    # Should insert a dummy assistant message with the tool call, followed by the tool response
    assert len(repaired) == 2
    assert repaired[0]["role"] == "assistant"
    assert repaired[0]["tool_calls"][0]["id"] == "call_123"
    assert repaired[1]["role"] == "tool"
    assert repaired[1]["content"] == "Success"


def test_unanswered_tool_call_fixed():
    # An assistant message with a tool call, but no tool response follows
    messages = [
        {"role": "user", "content": "Run command"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_123", "name": "run_command", "arguments": {}}],
        },
    ]
    repaired = _repair_message_sequence(messages)
    # Should append a dummy tool response at the end
    assert len(repaired) == 3
    assert repaired[2]["role"] == "tool"
    assert repaired[2]["tool_call_id"] == "call_123"
    assert "Error" in repaired[2]["content"]


def test_strict_alternation_enforced():
    # If we have user -> tool (which are both "user-side" roles in some APIs),
    # we want to make sure it alternates properly or matches API requirements.
    # In _repair_message_sequence, consecutive user-tool messages are merged or alternate.
    # Let's test a case where two user messages alternate with assistant dummy messages if they can't be merged.
    messages = [
        {"role": "user", "content": "Request 1"},
        {"role": "tool", "name": "run_command", "tool_call_id": "call_1", "content": "Res 1"},
    ]
    # Note: user followed by tool is a valid alternation sequence because user is user-side,
    # but some APIs require tool to follow assistant.
    # If we have user then tool, the tool is considered orphaned in our repair logic because there was no assistant tool call!
    # Let's check how it repairs:
    repaired = _repair_message_sequence(messages)
    assert len(repaired) == 3
    assert repaired[0]["role"] == "user"
    assert repaired[1]["role"] == "assistant"  # dummy assistant tool call inserted for orphaned tool response
    assert repaired[2]["role"] == "tool"
