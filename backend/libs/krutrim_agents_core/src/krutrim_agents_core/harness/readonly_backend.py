"""Back-compat shim.

`ReadOnlyFilesystemBackend` moved to `krutrim_agent_sandbox.backends.readonly`
when the sandbox backend base classes landed there. Import it from its new
home; this re-export keeps older import sites working.
"""

from __future__ import annotations

from krutrim_agent_sandbox.backends.readonly import ReadOnlyFilesystemBackend

__all__ = ["ReadOnlyFilesystemBackend"]
