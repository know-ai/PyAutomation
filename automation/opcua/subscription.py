import pytz
from datetime import datetime
from math import ceil
from ..singleton import Singleton
from ..tags.cvt import CVTEngine
from ..tags import Tag
from ..buffer import Buffer
from ..models import StringType
from ..logger.datalogger import DataLoggerEngine
import logging


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
            
            monitored_item = subscription.subscribe_data_change(
                node_id
            )

            self.monitored_items[client_name] = {
                node_id: {
                    "subscription": subscription,
                    "monitored_item": monitored_item,
                    "server": client_name
                }
            }

        else:

            if node_id not in self.monitored_items[client_name]:
            
                monitored_item = subscription.subscribe_data_change(
                    node_id
                )

                self.monitored_items[client_name].update({
                    node_id: {
                        "subscription": subscription,
                        "monitored_item": monitored_item,
                        "server": client_name
                    }
                })

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
        from .. import SEGMENT, MANUFACTURER, PyAutomation

        app = PyAutomation()

        timestamp = data.monitored_item.Value.SourceTimestamp
        if not timestamp:
            timestamp = datetime.now(pytz.utc)
        timestamp = timestamp.replace(tzinfo=pytz.UTC)
        tag_name = node.get_display_name().Text
        
        tag = self.app.get_tag_by_name(name=tag_name)
        if tag:
            if tag.get_value()!=val:

                val = tag.value.convert_value(value=val, from_unit=tag.get_unit(), to_unit=tag.get_display_unit())
                tag.value.set_value(value=val, unit=tag.get_display_unit())  
                if tag.manufacturer==MANUFACTURER and tag.segment==SEGMENT:      
                    self.app.cvt.set_value(id=tag.id, value=val, timestamp=timestamp)
                elif not MANUFACTURER and not SEGMENT:
                    self.app.cvt.set_value(id=tag.id, value=val, timestamp=timestamp) 
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
        self.cvt = CVTEngine()
        self.logger = DataLoggerEngine()
        self.buffer = dict()
        # self.last_notification_time = {}  # Para rastrear la última notificación de cada variable

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
        Documentation here
        """
        if client_name not in self.monitored_items:
            
            monitored_item = subscription.subscribe_data_change(
                node_id
            )
            self.monitored_items[client_name] = {
                node_id.get_display_name().Text: {
                    "subscription": subscription,
                    "monitored_item": monitored_item,
                    "server": client_name,
                    "namespace": node_id.nodeid.to_string()
                }
            }

        else:

            if node_id not in self.monitored_items[client_name]:
                
                monitored_item = subscription.subscribe_data_change(
                    node_id
                )

                self.monitored_items[client_name].update({
                    node_id.get_display_name().Text: {
                        "subscription": subscription,
                        "monitored_item": monitored_item,
                        "server": client_name,
                        "namespace": node_id.nodeid.to_string()
                    }
                })

    def unsubscribe(self, client_name:str, node_id):
        r"""
        Documentation here
        """
        if client_name in self.monitored_items:
            
            if node_id.get_display_name().Text in self.monitored_items[client_name]:
                
                node = self.monitored_items[client_name].pop(node_id.get_display_name().Text)
                item = node["monitored_item"]
                subscription = node["subscription"]
                subscription.unsubscribe(item)

    def resubscribe_all(self, client): 
        for client_name, monitored_items in self.monitored_items.items(): 
            for node_id, monitored_item in monitored_items.items(): 
                subscription = monitored_item["subscription"] 
                monitored_item["monitored_item"] = subscription.subscribe_data_change(client.get_node(node_id))

    # def check_subscription_status(self):
    #     """
    #     Verifica el estado de las suscripciones y detecta si alguna se ha perdido
    #     """
    #     namespaces = list()
    #     current_time = datetime.now(pytz.UTC)
    #     for client_name, items in self.monitored_items.items():
    #         for node_name, item in items.items():
                
    #             if node_name not in self.last_notification_time:
    #                 self.last_notification_time[node_name] = current_time
    #                 continue
                
    #             # Si no hemos recibido notificaciones en los últimos 30 segundos
    #             if (current_time - self.last_notification_time[node_name]).total_seconds() > 30:
    #                 logging.warning(f"Posible pérdida de suscripción para {node_name} en {client_name}")

    #             namespaces.append(item["namespace"])

    #     return namespaces

    def datachange_notification(self, node, val, data):
        r"""
        Documentation here
        """
        from .. import SEGMENT, MANUFACTURER, TIMEZONE
        namespace = node.nodeid.to_string()
        timestamp = data.monitored_item.Value.SourceTimestamp
        if not timestamp:
            timestamp = datetime.now(pytz.utc)
        timestamp = timestamp.replace(tzinfo=pytz.UTC)
        
        # Actualizar el tiempo de la última notificación
        # self.last_notification_time[node.get_display_name().Text] = timestamp
        
        tag = self.cvt.get_tag_by_node_namespace(node_namespace=namespace)
        tag_name = tag.get_name()
        val = tag.value.convert_value(value=val, from_unit=tag.get_unit(), to_unit=tag.get_display_unit())
        tag.value.set_value(value=val, unit=tag.get_display_unit())  
        if tag.manufacturer==MANUFACTURER and tag.segment==SEGMENT:      
            val = self.cvt.set_value(id=tag.id, value=val, timestamp=timestamp)
        elif not MANUFACTURER and not SEGMENT:
            val = self.cvt.set_value(id=tag.id, value=val, timestamp=timestamp)
        timestamp = timestamp.astimezone(TIMEZONE)
        if tag_name in self.buffer:
            self.buffer[tag_name]["timestamp"](timestamp)
            self.buffer[tag_name]["values"](val)      
        
        