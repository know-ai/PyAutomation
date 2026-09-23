"""HMI attribute listing. O(N) on request, never on the tick."""

from __future__ import annotations

from asyncua import ua


def _access_bits(node) -> int:
    from .access.level import parse_access_level

    try:
        return parse_access_level(int(node.get_access_level()))
    except Exception:
        return 1


def list_attrs(server) -> list:
    attrs = []
    listings = getattr(server, "_node_listings", None) or {}
    listed = set()
    for key, rows in listings.items():
        if rows:
            attrs.extend(rows)
            listed.add(key)
    for key, node in server._ua_nodes.items():
        if key in listed:
            continue
        rows = getattr(node, "listing", None)
        if rows is not None:
            attrs.extend(rows)
            continue
        try:
            if node.get_node_class() != ua.NodeClass.Variable:
                continue
            browse = ""
            try:
                browse = node.get_browse_name().Name or ""
            except Exception:
                browse = ""
            display = ""
            try:
                display = node.get_display_name().Text or ""
            except Exception:
                display = ""
            label = browse or display
            parent = node.get_parent().get_browse_name().Name
            from .access.level import access_label

            bits = _access_bits(node)
            attrs.append({
                "name": f"{parent}.{label}",
                "namespace": node.nodeid.to_string(),
                "access_level": bits,
                "access_level_label": access_label(bits),
                "user_access_level": bits,
                "access_restrictions": 0,
            })
            for prop in node.get_properties():
                prop_bits = _access_bits(prop)
                attrs.append({
                    "name": f"{parent}.{label}.{prop.get_display_name().Text}",
                    "namespace": prop.nodeid.to_string(),
                    "access_level": prop_bits,
                    "access_level_label": access_label(prop_bits),
                    "user_access_level": prop_bits,
                    "access_restrictions": 0,
                })
        except Exception:
            continue
    return attrs
