# -*- coding: utf-8 -*-
"""pyhades/logger/machines.py
"""
from ..dbmodels import Machines, TagsMachines, Tags
from .core import BaseEngine, BaseLogger
from ..utils.decorators import logging_error_handler
from ..models import IntegerType, StringType
from ..tags.tag import Tag


class MachinesLogger(BaseLogger):

    def __init__(self):

        super(MachinesLogger, self).__init__()

    @logging_error_handler
    def create(
            self,
            name:str,
            interval:int,
            description:str,
            classification:str,
            buffer_size:int,
            buffer_roll_type:str,
            criticity:int,
            priority:int):
        r"""
        Documentation here
        """
        if self.get_db():

            Machines.create(
                name=name,
                interval=interval,
                description=description,
                classification=classification,
                buffer_size=buffer_size,
                buffer_roll_type=buffer_roll_type,
                criticity=criticity,
                priority=priority
            )

    @logging_error_handler
    def put(
        self,
        name:StringType,
        machine_interval:IntegerType=None,
        description:StringType=None,
        classification:StringType=None,
        buffer_size:IntegerType=None,
        buffer_roll_type:StringType=None,
        criticity:IntegerType=None,
        priority:IntegerType=None
        ):
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
            
        query = Machines.put(
            id=machine.id,
            **fields
        )

        return query
    
    @logging_error_handler
    def read_all(self):

        return Machines.read_all()
    
    @logging_error_handler
    def read_config(self):

        return Machines.read_config()
    
    @logging_error_handler
    def bind_tag(self, tag:Tag, machine, default_tag_name:str=None):

        TagsMachines.create(tag_name=tag.name, machine_name=machine.name.value, default_tag_name=default_tag_name)


    @logging_error_handler
    def unbind_tag(self, tag:Tag, machine):

        tag_from_db = Tags.get_or_none(name=tag.name)
        machine_from_db= Machines.get_or_none(name=machine.name.value)
        tags_machine = TagsMachines.get((TagsMachines.tag == tag_from_db) & (TagsMachines.machine == machine_from_db))
        tags_machine.delete_instance()
        # TagsMachines.delete().where
    

class MachinesLoggerEngine(BaseEngine):
    r"""
    Alarms logger Engine class for Tag thread-safe database logging.

    """

    def __init__(self):

        super(MachinesLoggerEngine, self).__init__()
        self.logger = MachinesLogger()

    @logging_error_handler
    def create(
        self,
        name:str,
        interval:int,
        description:str,
        classification:str,
        buffer_size:int,
        buffer_roll_type:str,
        criticity:int,
        priority:int
        ):

        _query = dict()
        _query["action"] = "create"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["interval"] = interval
        _query["parameters"]["classification"] = classification
        _query["parameters"]["description"] = description
        _query["parameters"]["buffer_size"] = buffer_size
        _query["parameters"]["buffer_roll_type"] = buffer_roll_type
        _query["parameters"]["criticity"] = criticity
        _query["parameters"]["priority"] = priority
        
        return self.query(_query)
    
    @logging_error_handler
    def put(
        self,
        name:StringType,
        machine_interval:IntegerType=None,
        description:StringType=None,
        classification:StringType=None,
        buffer_size:IntegerType=None,
        buffer_roll_type:StringType=None,
        criticity:IntegerType=None,
        priority:IntegerType=None
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

        return self.query(_query)

    @logging_error_handler
    def read_all(self):

        _query = dict()
        _query["action"] = "read_all"
        _query["parameters"] = dict()
        return self.query(_query)
    
    @logging_error_handler
    def read_config(self):

        _query = dict()
        _query["action"] = "read_config"
        _query["parameters"] = dict()
        return self.query(_query)
    
    @logging_error_handler
    def bind_tag(self, tag:Tag, machine, default_tag_name:str=None):

        _query = dict()
        _query["action"] = "bind_tag"
        _query["parameters"] = dict()
        _query["parameters"]["tag"] = tag
        _query["parameters"]["machine"] = machine
        _query["parameters"]["default_tag_name"] = default_tag_name
        return self.query(_query)
    
    @logging_error_handler
    def unbind_tag(self, tag:Tag, machine):

        _query = dict()
        _query["action"] = "unbind_tag"
        _query["parameters"] = dict()
        _query["parameters"]["tag"] = tag
        _query["parameters"]["machine"] = machine
        return self.query(_query)
    

