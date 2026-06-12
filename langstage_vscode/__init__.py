"""langstage-vscode — Python stdio sidecar for the VS Code chat extension.

The extension spawns ``python -m langstage_vscode`` (or the
``langstage-vscode-sidecar`` console script); the sidecar bridges a
LangGraph/deepagents agent to the chat participant over newline-delimited JSON.
"""
from .sidecar import main, run

__version__ = "0.1.0"

__all__ = ["main", "run", "__version__"]
