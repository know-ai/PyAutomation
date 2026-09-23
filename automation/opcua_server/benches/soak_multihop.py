"""Short multi-hop soak. SOAK_S defaults to 2. A full day is the same script with SOAK_S=86400."""

from __future__ import annotations

import os
import time
from types import SimpleNamespace


def main() -> None:
    from automation.opcua_server.propagation import FieldPropagationRouter, new_transaction

    seconds = float(os.environ.get("SOAK_S", "2"))
    loops = 0
    tag = SimpleNamespace(opcua_address="opc.tcp://127.0.0.1:4840", node_namespace="ns=2;s=soak")

    class _Writer:
        def write(self, url, node_id, value) -> str:
            return "ok"

    router = FieldPropagationRouter(_Writer())
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = router.route(tag, 1, new_transaction(source="field"))
        if result.code == "max_depth":
            loops += 1
        result = router.route(tag, 1, new_transaction(depth=4))
        if not result.ok and result.code == "max_depth":
            continue
        loops += 1
    print(f"OPCUA_MULTIHOP_WRITES_LOOP_DETECTED_TOTAL {loops}")
    if loops:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
