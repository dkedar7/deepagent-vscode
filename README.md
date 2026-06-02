<p align="center">
  <img src="assets/header.svg" alt="deepagent-vscode" width="100%">
</p>

# deepagent-vscode

Chat with your own **LangGraph / deepagents** agent from inside VS Code — in the
same chat panel as Copilot — via the `@deepagent` chat participant.

It has two parts in one repo:

- **`extension/`** — a TypeScript VS Code extension that registers the
  `@deepagent` chat participant and renders agent output in the chat view.
- **`deepagent_vscode/`** — a small Python **stdio sidecar** that loads your
  agent and streams its events. Built on
  [`langgraph-stream-parser`](https://github.com/dkedar7/langgraph-stream-parser),
  so it speaks the same typed event vocabulary as the other deep-agent surfaces
  (`cowork-dash`, `deepagent-lab`, `deepagent-code`).

```
┌─ VS Code chat panel ────────────────────────────┐
│  @deepagent  (TypeScript extension)              │
│        │  spawns                                 │
│        ▼                                          │
│  python -m deepagent_vscode   (stdio sidecar)    │
│        │  NDJSON over stdin/stdout               │
│        ▼                                          │
│  your LangGraph / deepagents agent               │
└──────────────────────────────────────────────────┘
```

> **Status: early (v0.1.0).** Requires `langgraph-stream-parser>=0.2` — once
> that's on PyPI the sidecar installs with `pip`. The extension is not yet on
> the VS Code Marketplace (run it from source for now), and interactive
> approval of human-in-the-loop interrupts is not wired into the chat UI yet
> (the sidecar already supports the round-trip).

## Install

### Sidecar (Python)

```bash
pip install deepagent-vscode
# or, for a quick try with the bundled default agent:
pip install "deepagent-vscode[demo]"
```

### Extension (from source, until it's on the Marketplace)

```bash
cd extension
npm install
npm run compile
```

Then press **F5** in VS Code (with the `extension/` folder open) to launch an
Extension Development Host with `@deepagent` available.

## Configure

In VS Code settings:

| Setting | Description | Default |
|---|---|---|
| `deepagent.agentSpec` | Your agent, as `path/to/agent.py:graph` or `module:graph` | _(required)_ |
| `deepagent.pythonPath` | Python interpreter that has `deepagent-vscode` installed | `python` |

Your agent is any LangGraph `CompiledGraph` (e.g. from `deepagents`), exported
under the name in the spec:

```python
# my_agent.py
from deepagents import create_deep_agent
graph = create_deep_agent(...)   # -> deepagent.agentSpec = "my_agent.py:graph"
```

## Usage

Open the chat panel and start a message with `@deepagent`:

```
@deepagent summarize the failing tests in this repo and propose a fix
```

The extension streams the agent's content, tool calls, reasoning, and todo
updates into the chat response.

## Sidecar protocol

The extension talks to the sidecar over newline-delimited JSON. You can drive it
directly for testing:

```bash
DEEPAGENT_AGENT_SPEC=./my_agent.py:graph python -m deepagent_vscode
```

**Commands** (client → sidecar), one JSON object per line:

```jsonc
{"type": "message",  "session_id": "s1", "content": "hello"}
{"type": "decision", "session_id": "s1", "decisions": [{"type": "approve"}]}
{"type": "shutdown"}
```

**Events** (sidecar → client) — the `event.to_dict()` shapes from
`langgraph-stream-parser`, plus a few protocol frames:

```jsonc
{"type": "ready"}                          // emitted once at startup
{"type": "ack", "ref": "message"}          // command accepted
{"type": "content", "content": "..."}      // assistant text
{"type": "tool_start", "name": "...", ...} // tool call
{"type": "tool_end", "name": "...", ...}   // tool result
{"type": "interrupt", "action_requests": [...]}  // human-in-the-loop
{"type": "complete"}                       // turn finished
{"type": "turn_end", "session_id": "s1"}
```

## Development

```bash
# Sidecar
pip install -e ".[dev]"
pytest

# Extension
cd extension
npm install
npm run compile
```

## License

MIT
