from pyhades.tags import CVTEngine


class SubHandler(object):
    r"""
    Subscription Handler. To receive events from server for a subscription
    data_change and event methods are called directly from receiving thread.
    Do not do expensive, slow or network operation there. Create another 
    thread if you need to do such a thing
    """
    tag_engine = CVTEngine()

    def datachange_notification(self, node, val, data):
        
        namespace = node.nodeid.to_string()
        tag_name = self.tag_engine.get_tagname_by_node_namespace(namespace)
        
        if tag_name is not None:
            
            self.tag_engine.write_tag(tag_name, val)