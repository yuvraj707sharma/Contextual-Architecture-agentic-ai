"""Tests for ReasoningDisplay — both Rich and ANSI modes."""

from agents.reasoning_display import (
    AGENT_STYLES,
    ReasoningDisplay,
    ReasoningStep,
    get_reasoning,
    reset_reasoning,
)


class TestReasoningStep:
    """Tests for the ReasoningStep dataclass."""

    def test_auto_timestamp(self):
        step = ReasoningStep(agent="scanner", message="test")
        assert step.timestamp > 0

    def test_explicit_timestamp(self):
        step = ReasoningStep(agent="scanner", message="test", timestamp=1234.0)
        assert step.timestamp == 1234.0


class TestReasoningDisplay:
    """Tests for ReasoningDisplay core functionality."""

    def test_emit_collects_steps(self):
        rd = ReasoningDisplay(streaming=False)
        rd.emit("scanner", "Scanning project...")
        rd.emit("planner", "Creating plan...")
        assert len(rd.steps) == 2
        assert rd.steps[0].agent == "scanner"
        assert rd.steps[1].agent == "planner"

    def test_suppress_blocks_output(self, capsys):
        rd = ReasoningDisplay(streaming=True)
        rd.suppress()
        rd.emit("scanner", "This should not print")
        captured = capsys.readouterr()
        assert "should not print" not in captured.out
        # But still collected
        assert len(rd.steps) == 1

    def test_unsuppress_resumes_output(self):
        rd = ReasoningDisplay(streaming=True)
        rd.suppress()
        rd.emit("scanner", "suppressed")
        rd.unsuppress()
        rd.emit("scanner", "visible")
        assert len(rd.steps) == 2

    def test_get_summary_empty(self):
        rd = ReasoningDisplay(streaming=False)
        assert rd.get_summary() == ""

    def test_get_summary_with_steps(self):
        rd = ReasoningDisplay(streaming=False)
        rd.emit("scanner", "Found 10 files")
        rd.emit("planner", "Creating plan")
        summary = rd.get_summary()
        assert "Scanner" in summary
        assert "Found 10 files" in summary
        assert "Planner" in summary

    def test_get_steps_for_agent(self):
        rd = ReasoningDisplay(streaming=False)
        rd.emit("scanner", "msg1")
        rd.emit("planner", "msg2")
        rd.emit("scanner", "msg3")
        scanner_steps = rd.get_steps_for_agent("scanner")
        assert len(scanner_steps) == 2
        assert all(s.agent == "scanner" for s in scanner_steps)

    def test_to_trace_data(self):
        rd = ReasoningDisplay(streaming=False)
        rd.emit("scanner", "msg1", detail="extra info")
        trace = rd.to_trace_data()
        assert len(trace) == 1
        assert trace[0]["agent"] == "scanner"
        assert trace[0]["message"] == "msg1"
        assert trace[0]["detail"] == "extra info"
        assert trace[0]["timestamp"] > 0

    def test_clear(self):
        rd = ReasoningDisplay(streaming=False)
        rd.emit("scanner", "msg1")
        rd.emit("planner", "msg2")
        assert len(rd.steps) == 2
        rd.clear()
        assert len(rd.steps) == 0


class TestAgentStyles:
    """Tests for agent style configuration."""

    def test_all_core_agents_have_styles(self):
        expected_agents = [
            "scanner", "historian", "architect", "planner",
            "implementer", "reviewer", "clarification",
        ]
        for agent in expected_agents:
            assert agent in AGENT_STYLES, f"Missing style for {agent}"

    def test_style_has_required_keys(self):
        for agent, style in AGENT_STYLES.items():
            assert "marker" in style, f"{agent} missing marker"
            assert "color" in style, f"{agent} missing color"
            assert "rich_style" in style, f"{agent} missing rich_style"


class TestGlobalSingleton:
    """Tests for get_reasoning/reset_reasoning module-level functions."""

    def test_get_reasoning_returns_instance(self):
        reset_reasoning()
        rd = get_reasoning(streaming=False)
        assert isinstance(rd, ReasoningDisplay)

    def test_get_reasoning_returns_same_instance(self):
        reset_reasoning()
        rd1 = get_reasoning(streaming=False)
        rd2 = get_reasoning(streaming=False)
        assert rd1 is rd2

    def test_reset_clears_instance(self):
        reset_reasoning()
        rd1 = get_reasoning(streaming=False)
        reset_reasoning()
        rd2 = get_reasoning(streaming=False)
        assert rd1 is not rd2


class TestSummaryIcons:
    """Tests that summary output includes agent icons."""

    def test_summary_has_icons_keys(self):
        rd = ReasoningDisplay(streaming=False)
        rd.emit("scanner", "Scanning...")
        summary = rd.get_summary()
        assert "\u25b8" in summary  # scanner marker (▸)
