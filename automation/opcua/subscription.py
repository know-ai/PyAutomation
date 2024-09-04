# from pyhades.tags import CVTEngine
from automation.singleton import Singleton


class SubHandler(Singleton):
    r"""
    Subscription Handler. To receive events from server for a subscription
    data_change and event methods are called directly from receiving thread.
    Do not do expensive, slow or network operation there. Create another 
    thread if you need to do such a thing
    """
    # tag_engine = CVTEngine()

    def __init__(self):
        
        self.nodes = list()
        self.subscriptions = list()
        self.monitred_items = dict()

    def subscribe(self, subscription, client_name, node_id):

        if subscription not in self.subscriptions:

            self.subscriptions.append(subscription)

        if client_name not in self.monitred_items:

            monitored_item = subscription.subscribe_data_change(
                node_id
            )
            self.monitred_items[client_name] = {
                node_id: monitored_item
            }

        else:

            if node_id not in self.monitred_items[client_name]:
            
                monitored_item = subscription.subscribe_data_change(
                    node_id
                )
                self.monitred_items[client_name] = {
                    node_id: monitored_item
            }

    def unsubscribe(self):

        for subscription in self.subscriptions:

            for client_name, monitored_items in self.monitred_items.items():

                for _, monitored_item in self.monitred_items[client_name].items():
                    try:
                        subscription.unsubscribe(monitored_item)
                    except Exception as err:

                        pass

        self.subscriptions = list()
        self.nodes = list()
        self.monitred_items = dict()            

    def datachange_notification(self, node, val, data):
        
        namespace = node.nodeid.to_string()
        print(f"Node: {node} - Value: {val}")
        # tag_name = self.tag_engine.get_tagname_by_node_namespace(namespace)
        
        # if tag_name is not None:
            
        #     self.tag_engine.write_tag(tag_name, val)