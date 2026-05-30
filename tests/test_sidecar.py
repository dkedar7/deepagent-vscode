"""Tests for the stdio sidecar command/event loop."""
import io
import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from deepagent_vscode.sidecar import run


# ── Fakes / fixtures ─────────────────────────────────────────────────


class FakeGraph:
    """Sync LangGraph-ish fake yielding canned single-mode 'updates' chunks."""

    def __init__(self, chunks_per_call: list[list[Any]]):
        self._chunks = chunks_per_call
        self._i = 0
        self.calls: list[dict] = []

    def stream(self, input_data, config=None, stream_mode="updates"):
        self.calls.append({"input": input_data, "config": config, "stream_mode": stream_mode})
        chunks = self._chunks[self._i]
        self._i += 1
        for c in chunks:
            yield c


@dataclass
class MockInterrupt:
    value: Any
    resumable: bool = True


CONTENT = {"agent": {"messages": [AIMessage(content="Hello there")]}}
TOOLCALL = {"agent": {"messages": [AIMessage(
    content="", tool_calls=[{"id": "c1", "name": "search", "args": {"q": "x"}}],
)]}}
TOOLRESULT = {"tools": {"messages": [ToolMessage(
    content="result ok", name="search", tool_call_id="c1",
)]}}
INTERRUPT = {"__interrupt__": (MockInterrupt(value={
    "action_requests": [{"name": "bash", "args": {"command": "ls"}, "tool_call_id": "c1"}],
    "review_configs": [{"allowed_decisions": ["approve", "reject"]}],
}),)}


def drive(graph, commands, **kw):
    """Feed JSON commands through run() and return parsed event dicts."""
    stdin = io.StringIO("".join(json.dumps(c) + "\n" for c in commands))
    stdout = io.StringIO()
    run(graph, stdin, stdout, stream_mode="updates", **kw)
    return [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]


# ── Tests ────────────────────────────────────────────────────────────


def test_ready_is_first_event():
    events = drive(FakeGraph([]), [{"type": "shutdown"}])
    assert events[0] == {"type": "ready"}


def test_message_turn_emits_content_and_terminals():
    graph = FakeGraph([[CONTENT]])
    events = drive(graph, [
        {"type": "message", "session_id": "s", "content": "hi"},
        {"type": "shutdown"},
    ])
    types = [e["type"] for e in events]
    assert types[0] == "ready"
    assert {"type": "ack", "ref": "message"} in events
    assert "content" in types
    assert "complete" in types
    assert any(e["type"] == "turn_end" and e["session_id"] == "s" for e in events)
    # thread_id wired from session_id
    assert graph.calls[0]["config"] == {"configurable": {"thread_id": "s"}}


def test_tool_lifecycle():
    graph = FakeGraph([[TOOLCALL, TOOLRESULT]])
    events = drive(graph, [
        {"type": "message", "session_id": "s", "content": "search"},
        {"type": "shutdown"},
    ])
    types = [e["type"] for e in events]
    assert "tool_start" in types
    assert "tool_end" in types


def test_interrupt_then_decision_resumes():
    graph = FakeGraph([[TOOLCALL, INTERRUPT], [TOOLRESULT]])
    events = drive(graph, [
        {"type": "message", "session_id": "s", "content": "run it"},
        {"type": "decision", "session_id": "s", "decisions": [{"type": "approve"}]},
        {"type": "shutdown"},
    ])
    types = [e["type"] for e in events]
    assert "interrupt" in types
    assert {"type": "ack", "ref": "decision"} in events
    assert "tool_end" in types
    # interrupt action_requests normalized to a 'tool' key
    interrupt = next(e for e in events if e["type"] == "interrupt")
    assert interrupt["action_requests"][0]["tool"] == "bash"
    # second call resumes with a Command
    from langgraph.types import Command
    assert isinstance(graph.calls[1]["input"], Command)


def test_invalid_json_reported():
    stdin = io.StringIO("not json\n")
    stdout = io.StringIO()
    run(FakeGraph([]), stdin, stdout, stream_mode="updates")
    events = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert any(e["type"] == "error" and "invalid JSON" in e["error"] for e in events)


def test_unknown_command_reported():
    events = drive(FakeGraph([]), [{"type": "nope"}, {"type": "shutdown"}])
    assert any(e["type"] == "error" and "unknown command" in e["error"] for e in events)


def test_empty_message_reported():
    events = drive(FakeGraph([]), [
        {"type": "message", "content": ""},
        {"type": "shutdown"},
    ])
    assert any(e["type"] == "error" and "content" in e["error"] for e in events)


def test_decision_without_list_reported():
    events = drive(FakeGraph([]), [{"type": "decision"}, {"type": "shutdown"}])
    assert any(e["type"] == "error" and "decisions" in e["error"] for e in events)


def test_graph_error_surfaced():
    class BoomGraph:
        def stream(self, *a, **k):
            raise RuntimeError("kaboom")
            yield  # pragma: no cover

    events = drive(BoomGraph(), [
        {"type": "message", "content": "go"},
        {"type": "shutdown"},
    ])
    err = [e for e in events if e["type"] == "error"]
    assert err and "kaboom" in err[-1]["error"]
