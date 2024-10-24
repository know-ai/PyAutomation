from math import ceil
from ..singleton import Singleton
from ..tags.cvt import CVTEngine
from ..tags import Tag
from ..buffer import Buffer
from ..logger.datalogger import DataLoggerEngine
        

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

    def datachange_notification(self, node, val, data):
        r"""
        Documentation here
        """
        pass
        

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
                    "server": client_name
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
                        "server": client_name
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

    def datachange_notification(self, node, val, data):
        r"""
        Documentation here
        """
        from .. import SEGMENT, MANUFACTURER
        namespace = node.nodeid.to_string()
        timestamp = data.monitored_item.Value.SourceTimestamp
        tag = self.cvt.get_tag_by_node_namespace(node_namespace=namespace)
        tag_name = tag.get_name()
        val = tag.value.convert_value(value=val, from_unit=tag.get_unit(), to_unit=tag.get_display_unit())
        tag.value.set_value(value=val, unit=tag.get_display_unit())  
        if tag.manufacturer==MANUFACTURER and tag.segment==SEGMENT:      
            self.cvt.set_value(id=tag.id, value=val, timestamp=timestamp)
        elif not MANUFACTURER and not SEGMENT:
            self.cvt.set_value(id=tag.id, value=val, timestamp=timestamp)
        self.buffer[tag_name]["timestamp"](timestamp)
        self.buffer[tag_name]["values"](val)
        
        