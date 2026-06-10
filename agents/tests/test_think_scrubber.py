"""Tests for StreamingThinkScrubber."""

import pytest
from agents.think_scrubber import StreamingThinkScrubber


def test_basic_scrubbing():
    scrubber = StreamingThinkScrubber()
    
    text = "Here is some clean text.<think>this is reasoning and should be hidden</think> And more clean text."
    result = scrubber.feed(text) + scrubber.flush()
    assert result == "Here is some clean text. And more clean text."


def test_multiple_reasoning_blocks():
    scrubber = StreamingThinkScrubber()
    
    text = "<think>first reasoning</think>Hello<thinking>second reasoning</thinking>World<thought>third</thought>!"
    result = scrubber.feed(text) + scrubber.flush()
    assert result == "HelloWorld!"


def test_streaming_chunks():
    scrubber = StreamingThinkScrubber()
    
    # Send text in chunks, starting the think block on a new line (block boundary)
    chunks = [
        "Hello world!\n",
        "<th",
        "ink>reasoning goes ",
        "here...",
        "</th",
        "ink> Done."
    ]
    
    result = []
    for chunk in chunks:
        result.append(scrubber.feed(chunk))
    result.append(scrubber.flush())
    
    final_text = "".join(result)
    assert final_text == "Hello world!\n Done."


def test_unfinished_block_discarded_on_flush():
    scrubber = StreamingThinkScrubber()
    
    result1 = scrubber.feed("Clean text.\n<think>This reasoning never closes")
    result2 = scrubber.flush()
    
    assert result1 == "Clean text.\n"
    assert result2 == ""


def test_orphan_close_tags():
    scrubber = StreamingThinkScrubber()
    
    text = "Clean text. </think> More clean text."
    result = scrubber.feed(text) + scrubber.flush()
    assert result == "Clean text. More clean text."
