# -*- coding: utf-8 -*-
"""pyhades/logger/machines.py
"""
from ..dbmodels import Machines, TagsMachines, Tags
from .core import BaseEngine, BaseLogger
from ..utils.decorators import db_rollback
from ..models import IntegerType, StringType, FloatType
from ..tags.tag import Tag


class MachinesLogger(BaseLogger):

    def __init__(self):

        super(MachinesLogger, self).__init__()

    @db_rollback
    def create(
            self,
            identifier:str,
            name:str,
            interval:int,
            description:str,
            classification:str,
            buffer_size:int,
            buffer_roll_type:str,
            criticity:int,
            priority:int,
            on_delay:int=None,
            threshold:float=None
            ):
        r"""
        Documentation here
        """
        if not self.check_connectivity():

            return None
        
        if hasattr(threshold, "value"):
            
            threshold = threshold.value
       
        Machines.create(
            identifier=identifier,
            name=name,
            interval=interval,
            description=description,
            classification=classification,
            buffer_size=buffer_size,
            buffer_roll_type=buffer_roll_type,
            criticity=criticity,
            priority=priority,
            on_delay=on_delay,
            threshold=threshold
        )

    @db_rollback
    def put(
        self,
        name:StringType,
        machine_interval:IntegerType=None,
        description:StringType=None,
        classification:StringType=None,
        buffer_size:IntegerType=None,
        buffer_roll_type:StringType=None,
        criticity:IntegerType=None,
        priority:IntegerType=None,
        on_delay:IntegerType=None,
        threshold:FloatType=None
        ):

        if not self.check_connectivity():
            
            return None

        fields = dict()
        machine = Machines.read_by_name(name=name.value)
        if machine_interval:
            
            fields["interval"] = machine_interval.value
        if description:
            fields["description"] = description.value
        if classification:
            fields["classification"] = classification.value
        if buffer_size:
            fields["buffer_size"] = buffer_size.value
        if buffer_roll_type:
            fields["buffer_roll_type"] = buffer_roll_type.value
        if criticity:
            fields["criticity"] = criticity.value
        if priority:
            fields["priority"] = priority.value
        if on_delay:
            fields["on_delay"] = on_delay.value
        if threshold:
            if hasattr(threshold.value, "value"):
                threshold.value = threshold.value.value
            fields["threshold"] = threshold.value
            
        query = Machines.put(
            id=machine.id,
            **fields
        )

        return query
    
    @db_rollback
    def read_all(self):
        if not self.check_connectivity():

            return list()
        
        return Machines.read_all()
    
    @db_rollback
    def read_config(self):
        if not self.check_connectivity():
            
            return None

        return Machines.read_config()
    
    @db_rollback
    def bind_tag(self, tag:Tag, machine, default_tag_name:str=None):
        if not self.check_connectivity():

            return None
            
        TagsMachines.create(tag_name=tag.name, machine_name=machine.name.value, default_tag_name=default_tag_name)

    @db_rollback
    def unbind_tag(self, tag:Tag, machine):
        if not self.check_connectivity():

            return None

        tag_from_db = Tags.get_or_none(name=tag.name)
        machine_from_db= Machines.get_or_none(name=machine.name.value)
        tags_machine = TagsMachines.get((TagsMachines.tag == tag_from_db) & (TagsMachines.machine == machine_from_db))
        tags_machine.delete_instance()    

class MachinesLoggerEngine(BaseEngine):
    r"""
    Alarms logger Engine class for Tag thread-safe database logging.

    """

    def __init__(self):

        super(MachinesLoggerEngine, self).__init__()
        self.logger = MachinesLogger()

    def create(
        self,
        identifier:str,
        name:str,
        interval:int,
        description:str,
        classification:str,
        buffer_size:int,
        buffer_roll_type:str,
        criticity:int,
        priority:int,
        on_delay:int=None,
        threshold:float=None
        ):

        _query = dict()
        _query["action"] = "create"
        _query["parameters"] = dict()
        _query["parameters"]["identifier"] = identifier
        _query["parameters"]["name"] = name
        _query["parameters"]["interval"] = interval
        _query["parameters"]["classification"] = classification
        _query["parameters"]["description"] = description
        _query["parameters"]["buffer_size"] = buffer_size
        _query["parameters"]["buffer_roll_type"] = buffer_roll_type
        _query["parameters"]["criticity"] = criticity
        _query["parameters"]["priority"] = priority
        _query["parameters"]["on_delay"] = on_delay
        _query["parameters"]["threshold"] = threshold
        
        return self.query(_query)
    
    def put(
        self,
        name:StringType,
        machine_interval:IntegerType=None,
        description:StringType=None,
        classification:StringType=None,
        buffer_size:IntegerType=None,
        buffer_roll_type:StringType=None,
        criticity:IntegerType=None,
        priority:IntegerType=None,
        on_delay:IntegerType=None,
        threshold:FloatType=None
        ):

        _query = dict()
        _query["action"] = "put"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["machine_interval"] = machine_interval
        _query["parameters"]["classification"] = classification
        _query["parameters"]["description"] = description
        _query["parameters"]["buffer_size"] = buffer_size
        _query["parameters"]["buffer_roll_type"] = buffer_roll_type
        _query["parameters"]["criticity"] = criticity
        _query["parameters"]["priority"] = priority
        _query["parameters"]["on_delay"] = on_delay
        _query["parameters"]["threshold"] = threshold

        return self.query(_query)

    def read_all(self):

        _query = dict()
        _query["action"] = "read_all"
        _query["parameters"] = dict()
        return self.query(_query)
    
    def read_config(self):

        _query = dict()
        _query["action"] = "read_config"
        _query["parameters"] = dict()
        return self.query(_query)
    
    def bind_tag(self, tag:Tag, machine, default_tag_name:str=None):

        _query = dict()
        _query["action"] = "bind_tag"
        _query["parameters"] = dict()
        _query["parameters"]["tag"] = tag
        _query["parameters"]["machine"] = machine
        _query["parameters"]["default_tag_name"] = default_tag_name
        return self.query(_query)
    
    def unbind_tag(self, tag:Tag, machine):

        _query = dict()
        _query["action"] = "unbind_tag"
        _query["parameters"] = dict()
        _query["parameters"]["tag"] = tag
        _query["parameters"]["machine"] = machine
        return self.query(_query)
    

