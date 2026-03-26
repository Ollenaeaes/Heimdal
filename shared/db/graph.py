"""FalkorDB graph client (singleton).

Provides a thin wrapper around the ``falkordb`` Python package for
executing Cypher queries against the Heimdal graph.

Usage::

    from shared.db.graph import get_graph

    g = get_graph()
    result = g.query("MATCH (v:Vessel {imo: $imo}) RETURN v", {"imo": "1234567"})
"""

from __future__ import annotations

import logging
from typing import Any

from falkordb import FalkorDB

from shared.config import settings

logger = logging.getLogger("shared.db.graph")

_client: FalkorDB | None = None
_graph: Any | None = None


def get_client() -> FalkorDB:
    """Return the singleton FalkorDB client."""
    global _client
    if _client is None:
        _client = FalkorDB(
            host=settings.falkordb.host,
            port=settings.falkordb.port,
        )
        logger.info(
            "falkordb_connected",
            extra={
                "host": settings.falkordb.host,
                "port": settings.falkordb.port,
            },
        )
    return _client


def get_graph():
    """Return the singleton graph handle for the Heimdal graph."""
    global _graph
    if _graph is None:
        client = get_client()
        _graph = client.select_graph(settings.falkordb.graph_name)
        logger.info(
            "falkordb_graph_selected",
            extra={"graph_name": settings.falkordb.graph_name},
        )
    return _graph


def close_graph() -> None:
    """Close the FalkorDB connection."""
    global _client, _graph
    _graph = None
    if _client is not None:
        _client.close()
        _client = None
        logger.info("falkordb_closed")
