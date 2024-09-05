from automation.singleton import Singleton
        

class SubHandler(Singleton):
    r"""
    Subscription Handler. To receive events from server for a subscription
    data_change and event methods are called directly from receiving thread.
    Do not do expensive, slow or network operation there. Create another 
    thread if you need to do such a thing
    """

    def __init__(self):
        
        self.monitored_items = dict()

    def subscribe(self, subscription, client_name, node_id, server):
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
                    "monitored_item": monitored_item
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
                        "server": server
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
        # namespace = node.nodeid.to_string()
        # timestamp = data.monitored_item.Value.SourceTimestamp
        pass

        