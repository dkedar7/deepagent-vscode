"""stdio sidecar bridging a LangGraph agent to the deepagent-vscode extension.

Reads newline-delimited JSON commands on stdin, runs the agent through
``langgraph-stream-parser``, and writes newline-delimited JSON events on
stdout. The events are exactly ``event.to_dict()`` shapes — the same wire
vocabulary every other deep-agent surface (FastAPI WebSocket/SSE, Jupyter, CLI)
emits — so the TS extension's dispatcher renders them the same way.

Commands (client -> sidecar), one JSON object per line:
    {"type": "message",  "session_id": "s1", "content": "..."}
    {"type": "decision", "session_id": "s1", "decisions": [{"type": "approve"}]}
    {"type": "shutdown"}

Events (sidecar -> client), one JSON object per line:
    {"type": "ready"}                          # once, at startup
    {"type": "ack", "ref": "message|decision"} # command accepted
    <event_to_dict(...)>                       # content/tool_start/tool_end/
                                               # reasoning/extraction/interrupt
    {"type": "complete"} | {"type": "error", "error": "..."}
    {"type": "turn_end", "session_id": "s1"}   # one turn finished
"""
from __future__ import annotations

import json
from typing import Any, Callable, Iterable, TextIO

from langgraph_stream_parser import (
    StreamParser,
    create_resume_input,
    event_to_dict,
    load_agent_spec,
    prepare_agent_input,
)

DEFAULT_STREAM_MODE = ["updates", "messages"]
DEFAULT_MAX_RESULT_LEN = 50_000


def run(
    graph: Any,
    stdin: Iterable[str],
    stdout: TextIO,
    *,
    stream_mode: str | list[str] = DEFAULT_STREAM_MODE,
    max_result_len: int = DEFAULT_MAX_RESULT_LEN,
) -> None:
    """Drive the command/event loop over the given streams.

    Factored out from ``main`` so it can be tested with in-memory streams and
    a fake graph. ``stdin`` is any line iterable; ``stdout`` needs ``write``.
    """
    mode = list(stream_mode) if isinstance(stream_mode, tuple) else stream_mode

    def emit(obj: dict[str, Any]) -> None:
        stdout.write(json.dumps(obj) + "\n")
        stdout.flush()

    emit({"type": "ready"})

    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError as e:
            emit({"type": "error", "error": f"invalid JSON: {e}"})
            continue

        ctype = cmd.get("type")
        if ctype == "shutdown":
            break

        session_id = cmd.get("session_id", "default")
        config = {"configurable": {"thread_id": session_id}}

        if ctype == "message":
            content = cmd.get("content", "")
            if not content:
                emit({"type": "error", "error": "message requires 'content'"})
                continue
            emit({"type": "ack", "ref": "message"})
            input_data = prepare_agent_input(message=content)
        elif ctype == "decision":
            decisions = cmd.get("decisions")
            if not isinstance(decisions, list):
                emit({"type": "error", "error": "decision requires 'decisions' list"})
                continue
            emit({"type": "ack", "ref": "decision"})
            input_data = create_resume_input(decisions=decisions)
        else:
            emit({"type": "error", "error": f"unknown command type: {ctype!r}"})
            continue

        _run_turn(graph, input_data, config, mode, max_result_len, emit)
        emit({"type": "turn_end", "session_id": session_id})


def _run_turn(
    graph: Any,
    input_data: Any,
    config: dict[str, Any],
    stream_mode: str | list[str],
    max_result_len: int,
    emit: Callable[[dict[str, Any]], None],
) -> None:
    """Stream one turn; the parser emits the terminal complete/error event."""
    parser = StreamParser(stream_mode=stream_mode)
    try:
        stream = graph.stream(input_data, config=config, stream_mode=stream_mode)
        for event in parser.parse(stream):
            emit(event_to_dict(event, max_result_len=max_result_len))
    except Exception as exc:  # noqa: BLE001 — surfaced to the client as an event
        emit({"type": "error", "error": f"{type(exc).__name__}: {exc}"})


def main(argv: list[str] | None = None) -> int:
    import argparse
    import os
    import sys

    parser = argparse.ArgumentParser(prog="deepagent-vscode-sidecar")
    parser.add_argument(
        "--agent",
        default=os.getenv("DEEPAGENT_AGENT_SPEC"),
        help="Agent spec 'path.py:var' or 'module:var' (or DEEPAGENT_AGENT_SPEC).",
    )
    parser.add_argument(
        "--workspace",
        default=os.getenv("DEEPAGENT_WORKSPACE_ROOT", "."),
        help="Workspace root (or DEEPAGENT_WORKSPACE_ROOT).",
    )
    args = parser.parse_args(argv)

    def fail(msg: str) -> int:
        sys.stdout.write(json.dumps({"type": "error", "error": msg}) + "\n")
        sys.stdout.flush()
        return 1

    if not args.agent:
        return fail("no agent spec (set DEEPAGENT_AGENT_SPEC or pass --agent)")

    os.environ.setdefault("DEEPAGENT_WORKSPACE_ROOT", args.workspace)
    try:
        graph = load_agent_spec(args.agent)
    except Exception as exc:  # noqa: BLE001
        return fail(f"failed to load agent {args.agent!r}: {type(exc).__name__}: {exc}")

    run(graph, sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
