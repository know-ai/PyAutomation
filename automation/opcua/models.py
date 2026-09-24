"""OPC UA field client. Network I/O runs on the asyncua loop, not on this thread."""

from datetime import datetime
import os
import re
import uuid
import logging
import time
import json
from enum import Enum

from asyncua import ua
from asyncua.ua.uatypes import NodeId

from ..utils import _colorize_message
from ..utils.opcua_audit import (
    failure_cooldown_seconds,
    record_opcua_connection_event,
)
from .asyncua_client import sync_adapter

_DAQ_TIMEOUT_MIN_S = 0.05
_DAQ_TIMEOUT_MAX_S = 5.0
_DAQ_TIMEOUT_DEFAULT_S = 0.5
_DAQ_BAD_AFTER_MISSES_DEFAULT = 3
_DAQ_BAD_AFTER_MISSES_MAX = 20
DAQ_READ_TIMEOUT_S = _DAQ_TIMEOUT_DEFAULT_S


def daq_read_timeout_s(environ=None) -> float:
    """Per-cycle OPC Read budget (seconds). Env ``AUTOMATION_DAQ_READ_TIMEOUT_S``.

    This is **not** ``scan_time`` / DAQ-1000 interval. Clamp 0.05–5.0; default 0.5.
    """
    env = environ if environ is not None else os.environ
    raw = env.get("AUTOMATION_DAQ_READ_TIMEOUT_S", str(_DAQ_TIMEOUT_DEFAULT_S))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = _DAQ_TIMEOUT_DEFAULT_S
    return max(_DAQ_TIMEOUT_MIN_S, min(_DAQ_TIMEOUT_MAX_S, value))


def daq_bad_after_misses(environ=None) -> int:
    """Consecutive confirmed empty reads before DAQ marks the PV BAD.

    A single in-flight Read is not a confirmed empty: it is applied on the next
    cycle. Env ``AUTOMATION_DAQ_BAD_AFTER_MISSES`` (1–20, default 3).
    """
    env = environ if environ is not None else os.environ
    raw = env.get("AUTOMATION_DAQ_BAD_AFTER_MISSES", str(_DAQ_BAD_AFTER_MISSES_DEFAULT))
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = _DAQ_BAD_AFTER_MISSES_DEFAULT
    return max(1, min(_DAQ_BAD_AFTER_MISSES_MAX, value))


def _scope_owns_node(owner_node) -> bool:
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
    except (ImportError, AttributeError):
        return True
    if not getattr(scope, "enabled", False):
        return True
    if not getattr(scope, "is_valid", False):
        return False
    try:
        return bool(scope.owns_node(owner_node))
    except Exception:
        return False


class _NodeIdRef:
    def __init__(self, text: str) -> None:
        self._text = text
        parsed = ua.NodeId.from_string(text) if text else ua.NodeId()
        self.NamespaceIndex = parsed.NamespaceIndex
        self.Identifier = parsed.Identifier
        self.NamespaceUri = getattr(parsed, "NamespaceUri", None)

    def to_string(self) -> str:
        return self._text


class NodeRef:
    """Local stand-in for an OPC node. It does not touch the socket."""

    def __init__(self, namespace: str) -> None:
        self.nodeid = _NodeIdRef(str(namespace))


def _node_text(node) -> str:
    if node is None:
        return "ns=0;i=85"
    if isinstance(node, str):
        return node
    nodeid = getattr(node, "nodeid", node)
    if hasattr(nodeid, "to_string"):
        try:
            return nodeid.to_string()
        except Exception:
            pass
    return str(nodeid)


class Client:
    """Field client. ``uses_asyncua_runner`` tells DAS to enqueue instead of calling opcua."""

    uses_asyncua_runner = True

    def __init__(self, url, client_name: str, timeout=60, owner_node: str = None, username: str = None, password: str = None):
        self._id = None
        self._server_url = url
        self._timeout = timeout
        self.name = client_name
        self.owner_node = owner_node
        self._username = username or None
        self._password = password or None
        self._client = None
        self._is_open = False
        self._opc_ua_tree = dict()
        self._connection_state = "unknown"
        self._reconnect_attempts = 0
        self._reconnect_in_progress = False
        self._last_failure_event_monotonic = 0.0
        self._audit_source = "client-connect"
        self._suppress_connection_alarm = False
        self._manual_hold = False
        self._awaiting_embedded = False
        self._inflight = {}

    def get_id(self):
        return self._id

    def is_token_valid(self):
        """Security policy is not active. A connected session is the token check."""
        return self.is_connected()

    def _should_log_failure_event(self) -> bool:
        now = time.monotonic()
        if (now - self._last_failure_event_monotonic) >= failure_cooldown_seconds():
            self._last_failure_event_monotonic = now
            return True
        return False

    def _audit_connection(self, action: str, reason: str = "", error: str = "") -> None:
        record_opcua_connection_event(
            action=action,
            client_name=getattr(self, "name", "") or "",
            server_url=self._server_url or "",
            source=self._audit_source or "",
            reason=reason,
            error=error,
            attempts=self._reconnect_attempts if self._reconnect_in_progress or action.endswith("FAILED") else 0,
        )

    def _emit_opcua_socket(self, event_name: str, message: str) -> None:
        try:
            from automation import PyAutomation

            app = PyAutomation()
            if app.sio:
                app.sio.emit(
                    event_name,
                    data={
                        "message": message,
                        "client_name": self.name,
                        "url": self._server_url,
                        "server_url": self._server_url,
                        "manual_hold": bool(getattr(self, "_manual_hold", False)),
                    },
                )
        except Exception:
            logging.debug("OPC UA socket emit skipped", exc_info=True)

    def _sync_connection_alarm(self, disconnected: bool) -> None:
        if getattr(self, "_suppress_connection_alarm", False):
            return
        try:
            from ..utils.connection_alarms import set_opcua_disconnected

            set_opcua_disconnected(getattr(self, "name", "") or "", disconnected)
        except Exception:
            logging.debug("OPC UA connection alarm sync skipped", exc_info=True)
        if disconnected:
            self._mark_subscribed_tags_stale()

    def _mark_subscribed_tags_stale(self) -> None:
        try:
            from automation import PyAutomation

            app = PyAutomation()
            cvt = getattr(app, "cvt", None)
            if cvt is None or not hasattr(cvt, "mark_opcua_client_tags_stale"):
                return
            marked = cvt.mark_opcua_client_tags_stale(
                getattr(self, "name", "") or "",
                getattr(self, "_server_url", None),
            )
            if marked:
                logging.getLogger("pyautomation").info(
                    "OPC UA client=%s marked %s tags BAD/stale",
                    getattr(self, "name", None),
                    marked,
                )
        except Exception:
            logging.getLogger("pyautomation").debug("OPC UA stale tag mark skipped", exc_info=True)

    def connect(self):
        if not _scope_owns_node(getattr(self, "owner_node", None)):
            self._is_open = False
            self._connection_state = "disconnected"
            logging.getLogger("pyautomation").error(
                "OPC UA connection rejected for foreign owner client=%s owner_node=%s",
                self.name,
                getattr(self, "owner_node", None),
            )
            return {
                "message": "OPC UA client is not owned by this node",
                "url": self._server_url,
                "is_connected": False,
                "id": self.get_id(),
            }, 403
        self._manual_hold = False
        try:
            sync_adapter.open_session(
                self._server_url,
                self.name,
                self._timeout,
                username=getattr(self, "_username", None),
                password=getattr(self, "_password", None),
            )
            self._is_open = True
            self._id = str(uuid.uuid4())
            previous_state = self._connection_state
            self._connection_state = "connected"
            if self._reconnect_in_progress or previous_state == "disconnected":
                self._audit_connection("RECONNECTED", reason="session-restored")
            else:
                self._audit_connection("CONNECTED", reason="session-established")
            self._reconnect_attempts = 0
            self._last_failure_event_monotonic = 0.0
            self._sync_connection_alarm(disconnected=False)
            return {
                "message": "Successful connection",
                "url": self._server_url,
                "is_connected": self._is_open,
                "id": self.get_id(),
            }, 200
        except Exception as _err:
            str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger = logging.getLogger("pyautomation")
            error_text = f"{type(_err).__name__}: {_err}"
            logger.error(f"Error during OPCUA server {self._server_url} connection: {error_text}")
            print(_colorize_message(f"[{str_date}] [ERROR] Error during OPCUA server {self._server_url} connection", "ERROR"))
            self._is_open = False
            self._connection_state = "disconnected"
            if self._reconnect_in_progress:
                if self._should_log_failure_event():
                    self._audit_connection("RECONNECT_FAILED", reason="watchdog-retry", error=error_text)
            else:
                self._audit_connection("CONNECTION_FAILED", reason="initial-connect", error=error_text)
            self._sync_connection_alarm(disconnected=True)
            from .errors import classify_opcua_error

            return {
                "message": "Connection could not be established",
                "url": self._server_url,
                "is_connected": self._is_open,
                "id": self.get_id(),
                "error": error_text,
                "code": classify_opcua_error(error_text),
            }, 404

    def revolve_security_tokens(self):
        """asyncua renews the secure channel. There is no private socket to poke."""
        logging.getLogger("pyautomation").debug("security token renew is owned by asyncua client=%s", self.name)

    def reconnect(self):
        if getattr(self, "_manual_hold", False):
            return
        if not _scope_owns_node(getattr(self, "owner_node", None)):
            logging.getLogger("pyautomation").error(
                "OPC UA reconnect rejected for foreign owner client=%s owner_node=%s",
                self.name,
                getattr(self, "owner_node", None),
            )
            return
        if self.is_connected():
            return
        self._reconnect_unlocked()

    def _reconnect_unlocked(self):
        if self.is_connected():
            return
        from automation import PyAutomation

        app = PyAutomation()
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lost_link = self._connection_state == "connected"
        if lost_link:
            self._emit_opcua_socket("on.opcua.disconnected", f"Disconnected from {self._server_url}")
            self._audit_source = "watchdog-reconnect"
            self._audit_connection("DISCONNECTED", reason="connection-lost")
            self._connection_state = "disconnected"
            self._reconnect_attempts = 0
            self._sync_connection_alarm(disconnected=True)
        if self._connection_state == "unknown":
            self._connection_state = "disconnected"
        self._reconnect_in_progress = True
        self._audit_source = "watchdog-reconnect"
        self._reconnect_attempts += 1
        if self._reconnect_attempts == 1:
            logging.critical(f"Attempting to reconnect to OPCUA server {self._server_url}")
            print(_colorize_message(f"[{str_date}] [CRITICAL] Attempting to reconnect to OPCUA server {self._server_url}", "CRITICAL"))
            self._audit_connection("RECONNECTING", reason="watchdog")
        try:
            result, status = self.connect()
            if status == 200:
                app.das.reset_client(self.name)
                for _tag in app.cvt.iter_tags_for_opcua_client(self.name, self._server_url):
                    app.subscribe_opcua(
                        tag=_tag,
                        opcua_address=_tag.get_opcua_address(),
                        node_namespace=_tag.get_node_namespace(),
                        scan_time=_tag.get_scan_time(),
                        reload=True,
                    )
                self._emit_opcua_socket("on.opcua.connected", f"Connected to {self._server_url}")
                logging.critical(f"Reconnected to {self._server_url}")
                print(_colorize_message(f"[{str_date}] [INFO] Reconnected to OPCUA server {self._server_url}", "INFO"))
        except Exception as err:
            logging.critical(f"Reconnection to OPCUA server {self._server_url} failed: {err}")
            print(_colorize_message(f"[{str_date}] [CRITICAL] Reconnection to OPCUA server {self._server_url} failed...", "CRITICAL"))
            if self._should_log_failure_event():
                self._audit_connection(
                    "RECONNECT_FAILED",
                    reason="watchdog-exception",
                    error=f"{type(err).__name__}: {err}",
                )
        finally:
            self._reconnect_in_progress = False

    def __reset_object_attributes(self):
        self._server_url = None
        self._client = None
        self._opc_ua_tree = dict()

    def disconnect(self, retain_endpoint: bool = False):
        """Close the session. ``retain_endpoint`` keeps the URL and blocks watchdog reconnect."""
        server_url = self._server_url
        was_open = bool(self._is_open or self._connection_state == "connected")
        try:
            if retain_endpoint:
                self._manual_hold = True
            if self.name:
                sync_adapter.close_session(self.name)
            if was_open or self._connection_state != "disconnected":
                self._audit_connection("DISCONNECTED", reason="operator-hold" if retain_endpoint else "requested")
            self._connection_state = "disconnected"
            self._reconnect_attempts = 0
            self._is_open = False
            self._sync_connection_alarm(disconnected=True)
            if retain_endpoint:
                self._opc_ua_tree = {}
                self._emit_opcua_socket("on.opcua.disconnected", f"Disconnected from {server_url}")
            else:
                self.__reset_object_attributes()
            return {
                "message": "Successful disconnection",
                "url": server_url,
                "is_connected": False,
                "manual_hold": bool(self._manual_hold),
            }, 200
        except Exception as _err:
            error_text = f"{type(_err).__name__}: {_err}"
            if was_open and self._should_log_failure_event():
                self._audit_connection("DISCONNECTED", reason="disconnect-error", error=error_text)
            self._connection_state = "disconnected"
            self._sync_connection_alarm(disconnected=True)
            return {"message": "Disconnect could not be performed", "error": error_text}, 404

    def get_opc_ua_tree(self):
        try:
            if self.is_connected():
                children = self.browse_tree_generic(self.get_objects_node())
                return {"Objects": children}, 200
        except Exception as _err:
            result = {"message": str(_err)}
            return result, 500
        return {}, 400

    def get_values(self, nodes: list):
        if not self.is_connected():
            return [], 400
        names = [_node_text(node) for node in nodes]
        payload = self.read_data_values_bounded(names)
        if not isinstance(payload, dict):
            return [], 400
        result = []
        for namespace in names:
            data_value = payload.get(namespace)
            value = None
            timestamp = None
            if data_value is not None:
                try:
                    value = data_value.Value.Value
                    timestamp = data_value.SourceTimestamp
                except Exception:
                    value = data_value
            result.append({"Namespace": namespace, "Value": value, "Timestamp": timestamp})
        return result, 200

    def get_nodes_id_by_namespaces(self, namespaces: list):
        if not self.is_connected():
            return []
        return [NodeRef(namespace) for namespace in namespaces]

    def get_node_id_by_namespace(self, namespace: str):
        if self.is_connected() and namespace:
            return NodeRef(namespace)
        return None

    def get_node(self, nodeid):
        return NodeRef(_node_text(nodeid))

    def get_objects_node(self):
        return NodeRef("ns=0;i=85")

    def get_root_node(self):
        return NodeRef("ns=0;i=84")

    def get_nodes_values(self, namespaces: list) -> list:
        if not self.is_connected():
            return []
        payload = self.read_data_values_bounded(list(namespaces))
        if not isinstance(payload, dict):
            return []
        result = []
        for namespace in namespaces:
            data_value = payload.get(str(namespace))
            value = None
            if data_value is not None:
                try:
                    value = data_value.Value.Value
                except Exception:
                    value = data_value
            result.append({"Namespace": namespace, "Value": value})
        return result

    def write_value(self, node_namespace: str, value):
        try:
            if not self.is_connected():
                return {"message": "Cliente no conectado al servidor", "namespace": node_namespace, "success": False}, 400
            sync_adapter.write_value(self.name, node_namespace, value)
            return {"message": "Valor escrito exitosamente", "namespace": node_namespace, "value": value, "success": True}, 200
        except Exception as err:
            logging.getLogger("pyautomation").error(f"Error escribiendo valor en {node_namespace}: {err}")
            message = str(err)
            status = 400 if message.startswith("not-variable") else 500
            return {"message": f"Error al escribir valor: {message}", "namespace": node_namespace, "success": False}, status

    @staticmethod
    def find_servers(hostname, port):
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        url = f"opc.tcp://{hostname}:{port}"
        try:
            logging.info(f"Searching OPCUA servers in {url}")
            print(_colorize_message(f"[{str_date}] [INFO] Searching OPCUA servers in {url}", "INFO"))
            servers = sync_adapter.discover(url, "servers") or []
            logging.info(f"OPCUA servers found: {len(servers)}")
            print(_colorize_message(f"[{str_date}] [INFO] OPCUA servers found: {len(servers)}", "INFO"))
        except Exception:
            logging.error(f"Error searching OPCUA servers in {url}, Make sure the server is running and the port is correct")
            print(_colorize_message(f"[{str_date}] [ERROR] Error searching OPCUA servers in {url}, Make sure the server is running and the port is correct", "ERROR"))
            return []
        found = []
        for server in servers:
            found.append(
                {
                    "ApplicationUri": getattr(server, "ApplicationUri", None),
                    "ProductUri": getattr(server, "ProductUri", None),
                    "ApplicationName": getattr(getattr(server, "ApplicationName", None), "Text", None),
                    "ApplicationType": getattr(getattr(server, "ApplicationType", None), "name", None),
                    "GatewayServerUri": getattr(server, "GatewayServerUri", None),
                    "DiscoveryProfileUri": getattr(server, "DiscoveryProfileUri", None),
                    "DiscoveryUrls": getattr(server, "DiscoveryUrls", None),
                }
            )
        return found

    @staticmethod
    def get_endpoints(hostname, port):
        url = f"opc.tcp://{hostname}:{port}"
        try:
            endpoints = sync_adapter.discover(url, "endpoints") or []
            collected = []
            for endpoint in endpoints:
                discovery = getattr(getattr(endpoint, "Server", None), "DiscoveryUrls", None)
                if isinstance(discovery, list):
                    collected.extend(discovery)
                elif discovery:
                    collected.append(discovery)
            collected = [item for item in dict.fromkeys(collected) if str(item).startswith("opc.tcp")]
            result = [re.sub("//.*?/", f"//{hostname}:{port}/", item) for item in collected]
            return {"message": "Successful search", "endpoints": result}, 200
        except Exception:
            return {"message": "Unsuccessful search", "endpoints": []}, 400

    def is_connected(self):
        try:
            return bool(sync_adapter.is_connected(self.name))
        except Exception:
            return False

    def get_node_data_value(self, node_namespace):
        payload = self.read_data_values_bounded([node_namespace])
        if not isinstance(payload, dict):
            return None
        return payload.get(str(node_namespace))

    def read_data_value_bounded(self, node_namespace, timeout_s: float = None):
        budget = daq_read_timeout_s() if timeout_s is None else float(timeout_s)
        result = self.read_data_values_bounded([node_namespace], timeout_s=budget)
        if not isinstance(result, dict):
            return None
        return result.get(str(node_namespace))

    def read_data_values_bounded(self, namespaces, timeout_s: float = None):
        """One OPC Read for all NodeIds. ``None`` means the Read is still in flight."""
        budget = daq_read_timeout_s() if timeout_s is None else float(timeout_s)
        names = [str(ns) for ns in (namespaces or []) if ns]
        if not names:
            return {}
        if not self.is_connected():
            return {ns: None for ns in names}
        if not hasattr(self, "_inflight"):
            self._inflight = {}
        return sync_adapter.read_batch(self.name, names, budget, self._inflight)

    def get_node_attributes(self, node_namespace) -> dict:
        if not self.is_connected():
            return {}, 400
        try:
            payload = sync_adapter.browse(
                self.name,
                str(node_namespace),
                "attributes",
                depth=0,
                max_nodes=1,
                include_properties=False,
                include_property_values=False,
                timeout=max(1.0, daq_read_timeout_s()),
            )
        except Exception:
            return {}, 400
        if not isinstance(payload, dict):
            return {}, 400
        return payload, 200

    def get_nodes_attributes(self, namespaces: list) -> list:
        return [self.get_node_attributes(namespace) for namespace in namespaces if self.is_connected()]

    def get_referenced_nodes(self, node_id):
        if not self.is_connected():
            return [], 400
        try:
            children = self.browse_children_generic(NodeRef(node_id), include_properties=False)
        except Exception:
            return [], 400
        result = [("Organizes", item.get("title")) for item in children]
        return result, 200

    @staticmethod
    def _to_jsonable(value, _visited=None):
        if _visited is None:
            _visited = set()
        obj_id = id(value)
        if obj_id in _visited:
            return None
        _visited.add(obj_id)
        try:
            json.dumps(value)
            _visited.remove(obj_id)
            return value
        except Exception:
            pass
        if value is None:
            _visited.remove(obj_id)
            return None
        if isinstance(value, datetime):
            _visited.remove(obj_id)
            return value.isoformat()
        if isinstance(value, (bytes, bytearray)):
            _visited.remove(obj_id)
            return value.hex()
        if isinstance(value, Enum):
            _visited.remove(obj_id)
            return value.name
        if isinstance(value, NodeId):
            _visited.remove(obj_id)
            return value.to_string()
        if hasattr(value, "Low") and hasattr(value, "High"):
            try:
                out = {"Low": Client._to_jsonable(value.Low, _visited), "High": Client._to_jsonable(value.High, _visited)}
                _visited.remove(obj_id)
                return out
            except Exception:
                pass
        if hasattr(value, "Text") and hasattr(value, "Locale"):
            try:
                out = {"Text": value.Text, "Locale": value.Locale}
                _visited.remove(obj_id)
                return out
            except Exception:
                pass
        if hasattr(value, "Name") and hasattr(value, "NamespaceIndex"):
            try:
                out = {"Name": value.Name, "NamespaceIndex": int(value.NamespaceIndex)}
                _visited.remove(obj_id)
                return out
            except Exception:
                pass
        if isinstance(value, (list, tuple)):
            out = [Client._to_jsonable(item, _visited) for item in value]
            _visited.remove(obj_id)
            return out
        if isinstance(value, dict):
            out = {str(key): Client._to_jsonable(item, _visited) for key, item in value.items()}
            _visited.remove(obj_id)
            return out
        if hasattr(value, "__dict__"):
            try:
                out = {}
                for key, item in value.__dict__.items():
                    if str(key).startswith("_"):
                        continue
                    out[str(key)] = Client._to_jsonable(item, _visited)
                _visited.remove(obj_id)
                return out
            except Exception:
                pass
        _visited.remove(obj_id)
        return str(value)

    def browse_tree(self, node):
        if not self.is_connected():
            return []
        return self.browse_tree_generic(node)

    def browse_tree_generic(
        self,
        node,
        *,
        max_depth: int = 10,
        max_nodes: int = 50_000,
        include_properties: bool = True,
        include_property_values: bool = False,
        _depth: int = 0,
        _visited_nodeids=None,
        _count=None,
    ):
        if not self.is_connected():
            return []
        try:
            payload = sync_adapter.browse(
                self.name,
                _node_text(node),
                "tree",
                depth=max(0, int(max_depth) - int(_depth)),
                max_nodes=int(max_nodes),
                include_properties=bool(include_properties),
                include_property_values=bool(include_property_values),
            )
        except Exception:
            logging.getLogger("pyautomation").debug("browse tree failed", exc_info=True)
            return []
        return payload if isinstance(payload, list) else []

    def browse_children_generic(
        self,
        node,
        *,
        max_nodes: int = 5_000,
        include_properties: bool = True,
        include_property_values: bool = False,
    ):
        if not self.is_connected():
            return []
        try:
            payload = sync_adapter.browse(
                self.name,
                _node_text(node),
                "children",
                depth=0,
                max_nodes=int(max_nodes),
                include_properties=bool(include_properties),
                include_property_values=bool(include_property_values),
            )
        except Exception:
            return []
        return payload if isinstance(payload, list) else []

    def browse_variables_generic(
        self,
        node,
        *,
        max_depth: int = 20,
        max_nodes: int = 50_000,
        _depth: int = 0,
        _visited_nodeids=None,
        _count=None,
    ):
        if not self.is_connected():
            return []
        try:
            payload = sync_adapter.browse(
                self.name,
                _node_text(node),
                "variables",
                depth=max(0, int(max_depth) - int(_depth)),
                max_nodes=int(max_nodes),
                include_properties=False,
                include_property_values=False,
            )
        except Exception:
            return []
        return payload if isinstance(payload, list) else []

    def serialize(self):
        return {
            "client_id": self.get_id(),
            "server_url": self._server_url,
            "timeout": self._timeout,
            "is_opened": self.is_connected(),
            "manual_hold": bool(getattr(self, "_manual_hold", False)),
            "owner_node": getattr(self, "owner_node", None),
        }
