"""Access level cache. One batched read on the cold path.

One query when N <= 5000. Above that, chunks of 500.
Complexity: O(N) cache writes, O(ceil(N / chunk)) queries.
"""

from __future__ import annotations

from .level import parse_access_level

_CHUNK = 500
_SINGLE_QUERY_LIMIT = 5000
_DEFAULT = 1


def _stored_level(row) -> int:
    if row is None:
        return _DEFAULT
    if isinstance(row, dict):
        payload = row.get("access_level", _DEFAULT)
        try:
            return parse_access_level(payload)
        except ValueError:
            return _DEFAULT
    level = getattr(row, "access_level", None)
    if level is None and hasattr(row, "serialize"):
        level = row.serialize().get("access_level", _DEFAULT)
    try:
        return parse_access_level(level if level is not None else _DEFAULT)
    except ValueError:
        return _DEFAULT


class AccessControlService:
    """RAM cache of the integer bitmask. Complexity: resolve and remember are O(1)."""

    def __init__(self, cache: dict) -> None:
        self._cache = cache
        self.query_count = 0

    def resolve(self, namespace: str) -> int:
        """Complexity: O(1)."""
        try:
            return int(self._cache.get(namespace, _DEFAULT))
        except (TypeError, ValueError):
            return _DEFAULT

    def remember(self, namespace: str, access_level) -> None:
        """Complexity: O(1)."""
        try:
            self._cache[namespace] = parse_access_level(access_level)
        except ValueError:
            self._cache[namespace] = _DEFAULT

    def prefetch(self, namespaces: list[str]) -> dict[str, int]:
        """Load rows. Complexity: 1 query if N <= 5000, else ceil(N / 500)."""
        if not namespaces:
            return {}
        rows = self._load(namespaces)
        found = {}
        for row in rows:
            namespace = row.get("namespace") if isinstance(row, dict) else getattr(row, "namespace", None)
            if not namespace and hasattr(row, "serialize"):
                namespace = row.serialize().get("namespace")
            if namespace:
                found[namespace] = _stored_level(row)
        for namespace in namespaces:
            self._cache[namespace] = found.get(namespace, _DEFAULT)
        return {namespace: self._cache[namespace] for namespace in namespaces}

    def _load(self, namespaces: list[str]) -> list:
        try:
            from ...logger.opcua_server import OPCUAServerLogger
        except Exception:
            return []
        logger = OPCUAServerLogger()
        if len(namespaces) <= _SINGLE_QUERY_LIMIT:
            self.query_count += 1
            try:
                return list(logger.read_by_namespaces(namespaces) or [])
            except Exception:
                return []
        rows = []
        for offset in range(0, len(namespaces), _CHUNK):
            self.query_count += 1
            chunk = namespaces[offset : offset + _CHUNK]
            try:
                rows.extend(list(logger.read_by_namespaces(chunk) or []))
            except Exception:
                continue
        return rows
