"""Deprecated alias package: ``deepagent_vscode`` is now ``langstage_vscode``.

Kept for one transition window so existing imports and spawn commands keep
working. Import / spawn ``langstage_vscode`` instead.
"""
import sys as _sys
import warnings as _warnings

from langstage_vscode import sidecar  # noqa: F401

_warnings.warn(
    "deepagent_vscode has been renamed to langstage_vscode; "
    "this alias package will be removed in a future release.",
    DeprecationWarning,
    stacklevel=2,
)

_sys.modules[__name__ + ".sidecar"] = sidecar
