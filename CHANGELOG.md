# Changelog

All notable changes to this project will be documented in this file.

## [0.3.0] - 2026-06-12

**deepagent-vscode is now `langstage-vscode`** — the VS Code stage of the LangStage family ("every stage for your LangGraph agent").

### Changed

- Distribution `deepagent-vscode` → **`langstage-vscode`**; module `deepagent_vscode` → **`langstage_vscode`**. A deprecated alias package keeps `import deepagent_vscode` and `python -m deepagent_vscode` working (with a `DeprecationWarning`); the `deepagent-vscode-sidecar` command remains as an alias of `langstage-vscode-sidecar`.
- Extension: chat participant is **`@langstage`** (`langstage.agent`); settings move to `langstage.agentSpec` / `langstage.pythonPath` — the old `deepagent.*` settings are still read as deprecated fallbacks.
- Canonical config vocabulary via langgraph-stream-parser 0.3: `LANGSTAGE_*` env vars, project `langstage.toml`, global `~/.langstage/config.toml`; full legacy vocabulary still resolves.
- Parser pinned `>=0.3,<0.4`.


## [0.2.0] - 2026-06-10

First PyPI release of the sidecar (`pip install deepagent-vscode`).

### Added

- **Family-standard config chain** — the sidecar resolves through the shared `HostConfig`: defaults < `deepagents.toml` (global + project) < `DEEPAGENT_*` env < CLI flags. A project `deepagents.toml` with `[agent] spec = "..."` now just works.
- **`--demo`** — run with the shared keyless echo agent (`langgraph_stream_parser.demo.stub:graph`); no API key needed.
- **`--show-config`** — print each resolved value with its source and the env var / TOML key that sets it.
- **Extension**: an empty `deepagent.agentSpec` setting no longer hard-errors — the extension spawns the sidecar without `--agent` (cwd anchored at the workspace) and lets the config chain resolve.
- README: *One agent, every surface* family table.

### Changed

- `langgraph-stream-parser` pinned `>=0.2.2,<0.3`.

## [0.1.0] - 2026-06-04

Initial version (GitHub only): stdio sidecar bridging LangGraph agents to the `@deepagent` VS Code chat participant, speaking the `langgraph-stream-parser` `event.to_dict()` wire vocabulary.
