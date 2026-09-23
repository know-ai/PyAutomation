"""Field propagation and rollback. Complexity: O(1) plus one field wait."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from .access.contracts import IFieldWriter, IPropagationRouter, IRollbackService

MAX_PROPAGATION_DEPTH = 3


@dataclass(frozen=True)
class Transaction:
    """One external write. Complexity: O(1) to build."""

    transaction_id: str
    source: str
    depth: int
    originated_by: str


@dataclass(frozen=True)
class PropagationResult:
    """Outcome of one hop. Complexity: O(1)."""

    ok: bool
    status: str
    code: str = ""

    @staticmethod
    def skipped(reason: str) -> "PropagationResult":
        return PropagationResult(True, "skipped", reason)

    @staticmethod
    def rejected(reason: str) -> "PropagationResult":
        return PropagationResult(False, "rejected", reason)


class FieldPropagationRouter(IPropagationRouter):
    """Route an external CVT change to the PLC. Complexity: O(1) plus the writer."""

    def __init__(self, writer: IFieldWriter, rollback: IRollbackService | None = None) -> None:
        self.writer = writer
        self.rollback = rollback

    def route(self, tag, value, transaction: Transaction) -> PropagationResult:
        """Complexity: O(1) plus the field wait."""
        source = transaction.source
        if source == "field":
            return PropagationResult.skipped("field_origin")
        if source == "internal" or source == "rollback":
            return PropagationResult.skipped("internal_origin")
        if transaction.depth > MAX_PROPAGATION_DEPTH:
            return PropagationResult.rejected("max_depth")
        url = getattr(tag, "opcua_address", None)
        node_id = getattr(tag, "node_namespace", None)
        if not url or not node_id:
            return PropagationResult.skipped("no_binding")
        status = self.writer.write(str(url), str(node_id), value)
        if status == "ok":
            return PropagationResult(True, "ok")
        if status == "timeout":
            return PropagationResult(False, "timeout")
        if status == "disconnected":
            return PropagationResult(False, "disconnected")
        return PropagationResult(False, "rejected", str(status))


class CvtRollback(IRollbackService):
    """Write the previous value back without propagating it again. Complexity: O(1)."""

    def __init__(self, cvt) -> None:
        self.cvt = cvt

    def revert(self, tag, previous) -> None:
        """Complexity: O(1)."""
        from datetime import datetime, timezone

        self.cvt.set_value_fast(
            id=tag.id,
            value=previous,
            timestamp=datetime.now(timezone.utc),
            source="rollback",
        )


class ClientFieldWriter(IFieldWriter):
    """Reuse the connected field client. Complexity: O(1) plus the network wait."""

    def write(self, url: str, node_id: str, value):
        """Return ok, timeout, disconnected or rejected. Complexity: O(1) plus the wait."""
        try:
            from .. import PyAutomation

            client = PyAutomation().get_opcua_client_by_address(url)
        except Exception:
            return "disconnected"
        if client is None:
            return "disconnected"
        try:
            payload, status = client.write_value(node_id, value)
        except TimeoutError:
            return "timeout"
        except Exception as exc:
            text = str(exc).lower()
            if "timeout" in text:
                return "timeout"
            if "connect" in text or "disconnected" in text:
                return "disconnected"
            return "rejected"
        if status == 200 and isinstance(payload, dict) and payload.get("success", True):
            return "ok"
        message = ""
        if isinstance(payload, dict):
            message = str(payload.get("message") or "").lower()
        if status == 504 or "timeout" in message:
            return "timeout"
        if "no conectado" in message or "connect" in message:
            return "disconnected"
        return "rejected"


def new_transaction(source: str = "external", depth: int = 1, originated_by: str = "scada") -> Transaction:
    """Complexity: O(1)."""
    return Transaction(uuid.uuid4().hex, source, depth, originated_by)


def http_status(result: PropagationResult) -> int:
    """Map a field result to HTTP. Complexity: O(1)."""
    if result.ok:
        return 200
    if result.status == "timeout":
        return 504
    if result.status == "disconnected":
        return 503
    return 400
