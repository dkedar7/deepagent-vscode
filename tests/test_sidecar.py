"""Tests for the stdio sidecar command/event loop."""
import io
import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from langstage_vscode.sidecar import main, run


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


# ── main(): config resolution + --demo / --show-config ───────────────


def _isolate_config(monkeypatch, tmp_path):
    """Point cwd + the global config home at an empty tmp dir and strip
    legacy + canonical env so main() resolves from pure defaults."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LANGSTAGE_CONFIG_HOME", str(tmp_path))
    for var in ("LANGSTAGE_AGENT_SPEC", "DEEPAGENT_AGENT_SPEC", "LANGSTAGE_WORKSPACE_ROOT", "DEEPAGENT_WORKSPACE_ROOT"):
        monkeypatch.delenv(var, raising=False)


def test_main_show_config(monkeypatch, tmp_path, capsys):
    _isolate_config(monkeypatch, tmp_path)
    assert main(["--show-config"]) == 0
    assert "LANGSTAGE_AGENT_SPEC" in capsys.readouterr().out


def test_main_no_spec_emits_error(monkeypatch, tmp_path, capsys):
    _isolate_config(monkeypatch, tmp_path)
    assert main([]) == 1
    err = json.loads(capsys.readouterr().out.strip())
    assert err["type"] == "error"
    assert "langstage.toml" in err["error"]


def test_main_demo_conflicts_with_agent(monkeypatch, tmp_path, capsys):
    _isolate_config(monkeypatch, tmp_path)
    assert main(["--demo", "--agent", "x.py:g"]) == 1
    err = json.loads(capsys.readouterr().out.strip())
    assert "mutually exclusive" in err["error"]


def test_main_toml_supplies_agent_spec(monkeypatch, tmp_path, capsys):
    """The langstage.toml resolver is actually wired in: [agent].spec from a
    project file reaches load_agent_spec with no flags or env."""
    _isolate_config(monkeypatch, tmp_path)
    (tmp_path / "langstage.toml").write_text(
        '[agent]\nspec = "langgraph_stream_parser.demo.stub:graph"\n'
    )
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"type": "shutdown"}) + "\n")
    )
    assert main([]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert events[0] == {"type": "ready"}


def test_main_legacy_toml_still_works(monkeypatch, tmp_path, capsys):
    """Pre-rename deepagents.toml keeps resolving as a deprecated fallback."""
    _isolate_config(monkeypatch, tmp_path)
    (tmp_path / "deepagents.toml").write_text(
        '[agent]\nspec = "langgraph_stream_parser.demo.stub:graph"\n'
    )
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"type": "shutdown"}) + "\n")
    )
    assert main([]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert events[0] == {"type": "ready"}


def test_legacy_module_import_warns():
    import sys

    import pytest as _pytest

    sys.modules.pop("deepagent_vscode", None)
    sys.modules.pop("deepagent_vscode.sidecar", None)
    with _pytest.warns(DeprecationWarning, match="langstage_vscode"):
        import deepagent_vscode  # noqa: F401
    import deepagent_vscode.sidecar as old_sidecar
    import langstage_vscode.sidecar as new_sidecar

    assert old_sidecar is new_sidecar


def test_main_demo_end_to_end(monkeypatch, tmp_path, capsys):
    """--demo answers a real message turn through the stub agent — no keys."""
    _isolate_config(monkeypatch, tmp_path)
    commands = (
        json.dumps({"type": "message", "session_id": "s", "content": "hi demo"})
        + "\n"
        + json.dumps({"type": "shutdown"})
        + "\n"
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(commands))
    assert main(["--demo"]) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    types = [e["type"] for e in events]
    assert "ready" in types and "complete" in types and "turn_end" in types
    content = "".join(e.get("content", "") for e in events if e["type"] == "content")
    assert "hi demo" in content


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
