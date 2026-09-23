"""Replay de la auditoría SPEC-AUDIT-OPCUA-ACCESSLEVEL-MULTIHOP.

No modifica el servidor de producto. Levanta dos servidores asyncua locales
y ejecuta cuatro escenarios:

  D.7  write aceptado, conteo de notificaciones e idle sin loop
  A.4  rechazo de write y bits de AccessLevel / UserAccessLevel
  E.12 ausencia de propagación hacia un segundo servidor (PLC)
  J.10 write a un nodo de campo solo lectura
  E.10 conexión a un PLC ya detenido
  AL   AccessControlService.apply_level no espera las corrutinas de asyncua

Uso:
  IDLE_S=8 ../../venv/bin/python audits/repro_accesslevel/run_scenarios.py
"""

from __future__ import annotations

import asyncio
import inspect
import os
import time
from datetime import datetime, timezone

from asyncua import Client, Server, ua


def _ival(data_value) -> int:
    return int(data_value.Value.Value)


async def _pair(node) -> tuple[int, int]:
    access = await node.read_attribute(ua.AttributeIds.AccessLevel)
    user = await node.read_attribute(ua.AttributeIds.UserAccessLevel)
    return _ival(access), _ival(user)


async def _restrictions(node):
    try:
        value = await node.read_attribute(ua.AttributeIds.AccessRestrictions)
        return _ival(value)
    except Exception as exc:
        return type(exc).__name__


async def _try_write(node, value):
    try:
        await node.write_value(value)
        return "accepted", await node.read_value()
    except Exception as exc:
        return type(exc).__name__, str(exc)


class _Count:
    def __init__(self) -> None:
        self.n = 0
        self.values: list = []

    def datachange_notification(self, node, val, data) -> None:
        del node, data
        self.n += 1
        self.values.append(val)


async def main() -> None:
    from automation.opcua_server.access import AccessControlService

    idle_s = float(os.environ.get("IDLE_S", "8"))
    server = Server()
    await server.init()
    server.set_endpoint("opc.tcp://127.0.0.1:4857/audit")
    index = await server.register_namespace("audit")
    await server.start()
    try:
        objects = server.nodes.objects
        node = await objects.add_variable(index, "PI_01", 0.0)
        print("SCENARIO AL before", await _pair(node))
        result = AccessControlService.apply_level(node, "ReadWrite")
        print(
            "SCENARIO AL apply_level_type",
            type(result).__name__,
            "is_coroutine",
            inspect.iscoroutine(result),
        )
        print("SCENARIO AL after_sync_apply", await _pair(node))
        await node.set_writable(True)
        print("SCENARIO AL after_set_writable", await _pair(node), "restrictions", await _restrictions(node))

        read_only = await objects.add_variable(index, "PI_RO", 10.0)
        await read_only.set_writable(False)
        user_deny = await objects.add_variable(index, "PI_USER", 0.0)
        await user_deny.set_writable(True)
        await user_deny.unset_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentWrite)
        print("SCENARIO A.4 ro_bits", await _pair(read_only))
        print("SCENARIO A.4 user_deny_bits", await _pair(user_deny))

        internal = await server.create_subscription(100, None)
        await internal.subscribe_data_change(node)

        client = Client("opc.tcp://127.0.0.1:4857/audit")
        await client.connect()
        try:
            remote = client.get_node(node.nodeid)
            watch = _Count()
            subscription = await client.create_subscription(100, watch)
            await subscription.subscribe_data_change(remote)
            await asyncio.sleep(0.3)
            base = watch.n
            print("SCENARIO D.7 write", await _try_write(remote, 150.0))
            await asyncio.sleep(0.3)
            after_first = watch.n
            print("SCENARIO D.7 write_same", await _try_write(remote, 150.0))
            await asyncio.sleep(0.3)
            after_same = watch.n
            print("SCENARIO A.4 write_ro", await _try_write(client.get_node(read_only.nodeid), 99.0))
            print("SCENARIO A.4 write_user", await _try_write(client.get_node(user_deny.nodeid), 99.0))
            stamped = ua.DataValue(ua.Variant(151.0, ua.VariantType.Double))
            stamped.StatusCode = ua.StatusCode(ua.StatusCodes.Uncertain)
            stamped.SourceTimestamp = datetime.now(timezone.utc)
            try:
                await remote.write_attribute(ua.AttributeIds.Value, stamped)
                print("SCENARIO A.4 status_timestamp", "accepted")
            except Exception as exc:
                print("SCENARIO A.4 status_timestamp", type(exc).__name__, exc)
            cpu_start = time.process_time()
            await asyncio.sleep(idle_s)
            print(
                "SCENARIO D.7 notify",
                base,
                after_first,
                after_same,
                watch.n,
                "values",
                watch.values,
                "cpu_s",
                round(time.process_time() - cpu_start, 4),
                "idle_s",
                idle_s,
            )
        finally:
            await client.disconnect()

        plc = Server()
        await plc.init()
        plc.set_endpoint("opc.tcp://127.0.0.1:4858/plc")
        plc_index = await plc.register_namespace("plc")
        await plc.start()
        try:
            field = await plc.nodes.objects.add_variable(plc_index, "FI_01", 50.0)
            await field.set_writable(True)
            field_client = Client("opc.tcp://127.0.0.1:4858/plc")
            await field_client.connect()
            try:
                before = await field_client.get_node(field.nodeid).read_value()
                print("SCENARIO E.12 plc_before", before)
                print("SCENARIO E.12 plc_after", await field_client.get_node(field.nodeid).read_value())
            finally:
                await field_client.disconnect()
        finally:
            await plc.stop()

        await _field_failures()
    finally:
        await server.stop()


async def _field_failures() -> None:
    """E.10 PLC caído y J.10 nodo de campo solo lectura. No toca el CVT."""
    plc = Server()
    await plc.init()
    plc.set_endpoint("opc.tcp://127.0.0.1:4859/plc")
    index = await plc.register_namespace("plc")
    await plc.start()
    try:
        node = await plc.nodes.objects.add_variable(index, "FI_01", 50.0)
        await node.set_writable(False)
        client = Client("opc.tcp://127.0.0.1:4859/plc")
        await client.connect()
        try:
            status, detail = await _try_write(client.get_node(node.nodeid), 150.0)
            print("SCENARIO J.10 write_read_only", status, detail, "stays", await client.get_node(node.nodeid).read_value())
        finally:
            await client.disconnect()
    finally:
        await plc.stop()

    client = Client("opc.tcp://127.0.0.1:4859/plc")
    try:
        await asyncio.wait_for(client.connect(), timeout=3)
        print("SCENARIO E.10 connect", "accepted")
        await client.disconnect()
    except Exception as exc:
        print("SCENARIO E.10 connect", type(exc).__name__, exc)


if __name__ == "__main__":
    asyncio.run(main())
