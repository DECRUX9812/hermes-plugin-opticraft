"""Opticraft — real optical design inside Hermes.

Six tools over a deterministic physics engine: a Sellmeier glass catalogue, an
exact meridional ray trace, a cemented-achromat optimizer, spot diagrams against
the Airy disc, and a build-tolerance check. Nothing is narrated; every number is
computed.

Import-safe: no state is created here, and the capability probe imports this
module in a bare interpreter.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR.parent))

try:  # loaded as a package by the plugin loader / capability probe
    from .opticraft.tools import SCHEMAS, make_handlers  # type: ignore
except ImportError:  # loaded as a bare module
    from opticraft.tools import SCHEMAS, make_handlers  # type: ignore

__all__ = ["register"]


def register(ctx: Any) -> None:
    """Wire the agent half: six tools in the ``opticraft`` toolset."""
    handlers = make_handlers()
    for name, handler in handlers.items():
        ctx.register_tool(
            name=name,
            toolset="opticraft",
            schema=SCHEMAS[name],
            handler=handler,
            description=SCHEMAS[name]["description"].split(".")[0],
            emoji="🔭",
        )
