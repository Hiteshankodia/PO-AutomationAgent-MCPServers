"""
Package containing **all MCP servers** used by the PO automation system.

It also exposes a small convenience helper that spins up a
`MultiServerMCPClient` using the JSON configuration found at
``config/mcp_config.json``.

Typical usage
-------------
>>> from mcp_servers import get_local_mcp_client
>>> mcp_client = get_local_mcp_client()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Any

from langchain_mcp_adapters.client import MultiServerMCPClient


def _load_mcp_config(config_path: str | Path = "config/mcp_config.json") -> Mapping[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"MCP config file not found: {path.resolve()}")
    return json.loads(path.read_text())


def get_local_mcp_client(config_path: str | Path = "config/mcp_config.json") -> MultiServerMCPClient:
    """
    Return a `MultiServerMCPClient` initialized with the server definitions
    located in *config_path*.

    Parameters
    ----------
    config_path : str | Path, optional
        Path to the JSON configuration file.  Defaults to ``config/mcp_config.json``.
    """
    cfg = _load_mcp_config(config_path)
    # Convert "supplier-service" → "supplier", etc. for the key names expected
    servers = {
        key.split("-")[0]: value for key, value in cfg.get("mcpServers", {}).items()
    }
    return MultiServerMCPClient(servers)


__all__: list[str] = ["get_local_mcp_client"]
