"""safe_probe: a small, fully-auditable HTTP probing tool.

It knows exactly one address (the gateway) and never the policy. stdlib-only on
purpose: the tool is the thing under test, so its entire attack surface must be
readable without pulling in third-party code.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
