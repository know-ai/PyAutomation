"""Embedded OPC UA server. One canonical address space, no legacy plane.

Contracts: identity helpers and the namespace URI.
"""

from .flags import namespace_uri, server_host
from .identity import canonicalize_name, make_node_id

__all__ = [
    "canonicalize_name",
    "make_node_id",
    "namespace_uri",
    "server_host",
]
