import logging, time, datetime
from .worker import BaseWorker
from ..opcua.subscription import DAS
from ..managers import AlarmManager
from ..tags.cvt import CVTEngine

class DASWorker(BaseWorker):
    
    def __init__(self, das:DAS, manager:AlarmManager, period:int=5.0):

        super(DASWorker, self).__init__()
        
        self._das = das
        self._manager = manager
        self._period = period
        self.cvt = CVTEngine()

    def run(self):
        r"""
        Documentation here
        """
        logging.critical("DAS worker start successfully!")
        while True:
    
            namespaces = self._das.check_subscription_status()
            print(f"Namespaces: {namespaces}")
            for namespace in namespaces:
                tag = self.cvt.get_tag_by_node_namespace(node_namespace=namespace)
                alarm = self._manager.get_alarm_by_tag(tag=tag.name)
                print(f"Tag: {tag}")
                print(f"Alarm: {alarm}")

            if self.stop_event.is_set():
                logging.critical("DAS worker shutdown successfully!")
                break

            time.sleep(self._period)

    def stop(self):
        pass

