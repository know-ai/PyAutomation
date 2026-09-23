"""Reconciliation recovers engines that never saw a transition mark."""

from __future__ import annotations

from ..handler import IWatchdogHandler


def _engine_name(engine) -> str:
    raw = getattr(engine, "name", "")
    return raw.value if hasattr(raw, "value") else str(raw)


class ReconcileWatchdogHandler(IWatchdogHandler):
    """O(E) scan of registered machines. Skips engines already dirty."""

    def on_tick(self, supervisor) -> None:
        return

    def on_transition(self, name: str, old_state: str, new_state: str) -> None:
        return

    def on_reconcile(self, supervisor) -> None:
        server = supervisor.server
        try:
            machines = server.machine.machine_manager.get_machines()
        except Exception:
            return
        for engine, _, _ in machines:
            name = _engine_name(engine)
            if not name or name == "OPCUAServer":
                continue
            if name in server._dirty_engines:
                continue
            server._dirty_engines.add(name)
            server.metrics.engine_watchdog_recoveries += 1
