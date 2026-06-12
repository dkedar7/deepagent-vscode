<p align="center">
  <img src="assets/header.svg" alt="langstage-vscode" width="100%">
</p>

# langstage-vscode

Chat with your own **LangGraph** agent from inside VS Code — in the
same chat panel as Copilot — via the `@langstage` chat participant.

> Renamed from **deepagent-vscode** (the old package name now just installs
> this one; `python -m deepagent_vscode` and the old sidecar command still work).

It has two parts in one repo:

- **`extension/`** — a TypeScript VS Code extension that registers the
  `@langstage` chat participant and renders agent output in the chat view.
- **`langstage_vscode/`** — a small Python **stdio sidecar** that loads your
  agent and streams its events. Built on
  [`langgraph-stream-parser`](https://github.com/dkedar7/langgraph-stream-parser),
  so it speaks the same typed event vocabulary as the other LangStage stages
  (`langstage`, `langstage-jupyter`, `langstage-cli`).

```
┌─ VS Code chat panel ────────────────────────────┐
│  @langstage  (TypeScript extension)              │
│        │  spawns                                 │
│        ▼                                          │
│  python -m langstage_vscode   (stdio sidecar)    │
│        │  NDJSON over stdin/stdout               │
│        ▼                                          │
│  your LangGraph / deepagents agent               │
└──────────────────────────────────────────────────┘
```

> **Status: early.** The extension is not yet on the VS Code Marketplace (run
> it from source for now), and interactive approval of human-in-the-loop
> interrupts is not wired into the chat UI yet (the sidecar already supports
> the round-trip).

## Every stage for your LangGraph agent

langstage-vscode is the VS Code stage of the **LangStage family**: write your agent once — any LangGraph `CompiledGraph` — and run it on every stage with the same spec string (`module:attr` or `path/to/file.py:attr`), the same `langstage.toml` config file, and the same `LANGSTAGE_*` environment variables.

| Stage | Package | Try it |
|---|---|---|
| Web app | [langstage](https://github.com/dkedar7/langstage) | `langstage run --agent my_agent.py:graph` |
| JupyterLab | [langstage-jupyter](https://github.com/dkedar7/langstage-jupyter) | `pip install langstage-jupyter`, then the chat sidebar in `jupyter lab` |
| Terminal | [langstage-cli](https://github.com/dkedar7/langstage-cli) | `langstage-cli -a my_agent.py:graph` |
| VS Code | langstage-vscode | **you are here** |
| Reference agent | [langstage-hermes](https://github.com/dkedar7/langstage-hermes) | `LANGSTAGE_AGENT_SPEC=langstage_hermes.agent:graph` on any stage |
| Shared core | [langgraph-stream-parser](https://github.com/dkedar7/langgraph-stream-parser) | typed events + config resolver behind every stage |

## Install

### Sidecar (Python)

```bash
pip install langstage-vscode
# or, for a quick try with the bundled default agent:
pip install "langstage-vscode[demo]"
```

### Extension (from source, until it's on the Marketplace)

```bash
cd extension
npm install
npm run compile
```

Then press **F5** in VS Code (with the `extension/` folder open) to launch an
Extension Development Host with `@langstage` available.

## Configure

In VS Code settings:

| Setting | Description | Default |
|---|---|---|
| `langstage.agentSpec` | Your agent, as `path/to/agent.py:graph` or `module:graph` | _(falls back to `LANGSTAGE_AGENT_SPEC` / `langstage.toml`)_ |
| `langstage.pythonPath` | Python interpreter that has `langstage-vscode` installed | `python` |

The sidecar resolves its configuration through the family-standard chain —
**defaults < `langstage.toml` (global + project) < `LANGSTAGE_*` env < CLI
flags** — so a project with `[agent] spec = "my_agent.py:graph"` in its
`langstage.toml` needs no VS Code setting at all. Inspect the resolved values:

```bash
langstage-vscode-sidecar --show-config
```

Your agent is any LangGraph `CompiledGraph` (e.g. from `deepagents`), exported
under the name in the spec:

```python
# my_agent.py
from deepagents import create_deep_agent
graph = create_deep_agent(...)   # -> langstage.agentSpec = "my_agent.py:graph"
```

## Usage

Open the chat panel and start a message with `@langstage`:

```
@langstage summarize the failing tests in this repo and propose a fix
```

The extension streams the agent's content, tool calls, reasoning, and todo
updates into the chat response.

## Sidecar protocol

The extension talks to the sidecar over newline-delimited JSON. You can drive it
directly for testing:

```bash
LANGSTAGE_AGENT_SPEC=./my_agent.py:graph python -m langstage_vscode

# or with no agent and no API key at all:
python -m langstage_vscode --demo
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
