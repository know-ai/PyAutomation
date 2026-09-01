# -*- coding: utf-8 -*-
"""Product HMI menu extensions. Framework stores items; it does not know iDetectFugas."""
from __future__ import annotations

from threading import Lock
from typing import Any, Dict, List

_LOCK = Lock()
_ITEMS: Dict[str, Dict[str, Any]] = {}


def register_menu_item(item: Dict[str, Any]) -> None:
    """Register or replace a sidebar entry. Required: id, path."""
    item_id = str(item.get("id") or "").strip()
    path = str(item.get("path") or "").strip()
    if not item_id or not path:
        raise ValueError("hmi extension requires id and path")
    payload = {
        "id": item_id,
        "path": path if path.startswith("/") else f"/{path}",
        "label_key": str(item.get("label_key") or item.get("label") or item_id),
        "icon": str(item.get("icon") or "bi bi-grid"),
        "priority": int(item.get("priority") or 100),
    }
    with _LOCK:
        _ITEMS[item_id] = payload


def list_menu_items() -> List[Dict[str, Any]]:
    with _LOCK:
        items = list(_ITEMS.values())
    items.sort(key=lambda row: (int(row.get("priority") or 100), str(row.get("id") or "")))
    return items


def clear_menu_items() -> None:
    with _LOCK:
        _ITEMS.clear()
