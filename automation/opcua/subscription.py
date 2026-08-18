import pytz
import threading
from datetime import datetime
from math import ceil
from ..singleton import Singleton
from ..tags.cvt import CVTEngine
from ..tags import Tag
from ..buffer import Buffer
from ..models import StringType
from ..logger.datalogger import DataLoggerEngine


def _scope_owns_tag(tag) -> bool:
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
    except (ImportError, AttributeError):
        return True
    if not getattr(scope, "enabled", False):
        return True
    if not getattr(scope, "is_valid", False) or tag is None:
        return False
    try:
        return bool(scope.owns_tag(tag))
    except Exception:
        return False


class SubHandler(Singleton):
    r"""
    Subscription Handler. To receive events from server for a subscription
    data_change and event methods are called directly from receiving thread.
    Do not do expensive, slow or network operation there. Create another 
    thread if you need to do such a thing
    """

    def __init__(self):
        
        self.monitored_items = dict()

    def subscribe(self, subscription, client_name, node_id):
        r"""
        Documentation here
        """
        
        if client_name not in self.monitored_items:
            self.monitored_items[client_name] = {}
        key = node_id.nodeid.to_string() if hasattr(node_id, "nodeid") else str(node_id)
        existing = self.monitored_items[client_name].get(key)
        if existing:
            try:
                existing["subscription"].unsubscribe(existing["monitored_item"])
            except Exception:
                pass
        monitored_item = subscription.subscribe_data_change(node_id)
        self.monitored_items[client_name][key] = {
            "subscription": subscription,
            "monitored_item": monitored_item,
            "server": client_name
        }

    def unsubscribe_all(self):
        r"""
        Documentation here
        """

        for _, monitored_items in self.monitored_items.items():

            for _, monitored_item in monitored_items.items():
                
                item = monitored_item["monitored_item"]
                subscription = monitored_item["subscription"]
                subscription.unsubscribe(item)
                
        self.monitored_items = dict()  

    def resubscribe_all(self, client): 
        for client_name, monitored_items in self.monitored_items.items(): 
            for node_id, monitored_item in monitored_items.items(): 
                subscription = monitored_item["subscription"] 
                monitored_item["monitored_item"] = subscription.subscribe_data_change(client.get_node(node_id))   

    def datachange_notification(self, node, val, data):
        r"""
        Documentation here
        """
        pass

class SubHandlerServer(Singleton):

    def __init__(self):
        from ..core import PyAutomation
        self.app = PyAutomation()
        self.subscriptions = dict()

    def is_property(self, node):
        from ..state_machine import ua
        # A property is a variable that is part of another node (often an Object or another Variable)
        parent = node.get_parent()
        references = node.get_references(refs=ua.ObjectIds.HasProperty)
        return bool(references)

    def is_variable(self, node):
        from ..state_machine import ua
        return node.get_node_class() == ua.NodeClass.Variable

    def datachange_notification(self, node, val, data):
        from .. import PyAutomation

        app = PyAutomation()

        timestamp = data.monitored_item.Value.SourceTimestamp
        if not timestamp:
            timestamp = datetime.now(pytz.utc)
        else:
            from ..timebase import ensure_utc
            timestamp = ensure_utc(timestamp)
        tag_name = node.get_display_name().Text
        
        tag = self.app.get_tag_by_name(name=tag_name)
        if tag:
            if not _scope_owns_tag(tag):
                return
            if tag.get_value()!=val:

                val = tag.value.convert_value(value=val, from_unit=tag.get_unit(), to_unit=tag.get_display_unit())
                self.app.cvt.set_value_fast(id=tag.id, value=val, timestamp=timestamp)
        else:
            
            parent = node.get_parent()
            if parent:
                machine_name = parent.get_display_name().Text
                machine = app.get_machine(name=StringType(machine_name))
                attr = getattr(machine, tag_name)
                attr.value = val
                

class DAS(Singleton):
    r"""
    Subscription Handler. To receive events from server for a subscription
    data_change and event methods are called directly from receiving thread.
    Do not do expensive, slow or network operation there. Create another 
    thread if you need to do such a thing
    """

    def __init__(self):
  
        self.monitored_items = dict()
        self.client_subscriptions = dict()
        self.cvt = CVTEngine()
        self.logger = DataLoggerEngine()
        self.buffer = dict()
        self._subscribe_lock = threading.Lock()

    def _node_key(self, node_id) -> str:
        try:
            return node_id.nodeid.to_string()
        except Exception:
            return str(node_id)

    def monitored_count(self) -> int:
        return sum(len(items) for items in self.monitored_items.values())

    def get_or_create_subscription(self, client, client_name: str, period: int = 1000):
        existing = self.client_subscriptions.get(client_name)
        if existing is not None:
            return existing
        subscription = client.create_subscription(period, self)
        self.client_subscriptions[client_name] = subscription
        return subscription

    def reset_client(self, client_name: str) -> None:
        items = self.monitored_items.pop(client_name, {})
        for record in items.values():
            try:
                record["subscription"].unsubscribe(record["monitored_item"])
            except Exception:
                pass
        subscription = self.client_subscriptions.pop(client_name, None)
        if subscription is not None:
            try:
                subscription.delete()
            except Exception:
                pass

    def restart_buffer(self, tag:Tag):
        r"""
        Documentation here
        """
        scan_time = tag.get_scan_time()
        if scan_time:
            
            self.buffer[tag.get_name()].update({
                "timestamp": Buffer(size=ceil(600/ ceil(scan_time / 1000))),
                "values": Buffer(size=ceil(600 / ceil(scan_time / 1000)))
            })
        else:
            self.buffer[tag.get_name()].update({
                "timestamp": Buffer(size=600),
                "values": Buffer(size=600)
            })

    def subscribe(self, subscription, client_name, node_id):
        r"""
        Adds ``node_id`` to the single subscription owned by ``client_name``.
        Keys are OPC UA namespace strings; an existing monitored item is
        unsubscribed before a replacement is created.
        """
        key = self._node_key(node_id)
        tag = self.cvt.get_tag_by_node_namespace(node_namespace=key)
        if not _scope_owns_tag(tag):
            return None
        tag_client = getattr(tag, "opcua_client_name", None)
        if tag_client and tag_client.lower() != (client_name or "").lower():
            return None
        with self._subscribe_lock:
            bucket = self.monitored_items.setdefault(client_name, {})
            existing = bucket.get(key)
            if existing:
                try:
                    existing["subscription"].unsubscribe(existing["monitored_item"])
                except Exception:
                    pass
            monitored_item = subscription.subscribe_data_change(node_id)
            bucket[key] = {
                "subscription": subscription,
                "monitored_item": monitored_item,
                "server": client_name,
                "namespace": key,
            }
        
        ## Trying to get the value of the tag into OPCUA Client
        try:
            val = node_id.get_value()
            self.update_tag_value(node=node_id, val=val)
        except Exception:
            pass

    def unsubscribe(self, client_name:str, node_id):
        r"""
        Documentation here
        """
        if client_name not in self.monitored_items:
            return
        key = self._node_key(node_id)
        bucket = self.monitored_items[client_name]
        record = bucket.pop(key, None)
        if record is None:
            display_name = None
            try:
                display_name = node_id.get_display_name().Text
            except Exception:
                display_name = None
            if display_name:
                record = bucket.pop(display_name, None)
        if record is None:
            return
        try:
            record["subscription"].unsubscribe(record["monitored_item"])
        except Exception:
            pass

    def resubscribe_all(self, client): 
        for client_name, monitored_items in self.monitored_items.items(): 
            for node_id, monitored_item in monitored_items.items(): 
                subscription = monitored_item["subscription"] 
                monitored_item["monitored_item"] = subscription.subscribe_data_change(client.get_node(node_id))

    def update_tag_value(self, node, val, timestamp=None):
        r"""
        Update tag value in CVT and buffer
        """
        from ..timebase import ensure_utc
        
        timestamp = ensure_utc(timestamp)
        
        namespace = node.nodeid.to_string()
        tag = self.cvt.get_tag_by_node_namespace(node_namespace=namespace)
        
        if tag and _scope_owns_tag(tag):
            tag_name = tag.get_name()
            val = tag.value.convert_value(value=val, from_unit=tag.get_unit(), to_unit=tag.get_display_unit())
            val = self.cvt.set_value_fast(id=tag.id, value=val, timestamp=timestamp)
            if val is not None and tag_name in self.buffer:
                self.buffer[tag_name]["timestamp"](timestamp)
                self.buffer[tag_name]["values"](val)

    def datachange_notification(self, node, val, data):
        r"""
        Documentation here
        """
        timestamp = data.monitored_item.Value.SourceTimestamp
        self.update_tag_value(node, val, timestamp)      
        
        