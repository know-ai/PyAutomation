# -*- coding: utf-8 -*-
"""automation/logger/machines.py

This module implements the Machines Logger, responsible for persisting State Machine
configurations and their bindings to Tags.
"""
from ..dbmodels import Machines, TagsMachines, Tags
from .core import BaseEngine, BaseLogger
from ..utils.decorators import db_rollback
from ..models import IntegerType, StringType, FloatType
from ..tags.tag import Tag


class MachinesLogger(BaseLogger):
    r"""
    Logger class specialized for State Machine persistence.
    """

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
        Creates a new State Machine definition in the database.

        **Parameters:**

        * **identifier** (str): Unique ID.
        * **name** (str): Machine name.
        * **interval** (int): Execution interval.
        * **description** (str): Description.
        * **classification** (str): Type of machine.
        * **buffer_size** (int): Size of internal buffer.
        * **buffer_roll_type** (str): Roll type (e.g., "fifo").
        * **criticity** (int): Criticality level.
        * **priority** (int): Priority level.
        * **on_delay** (int, optional): Delay before starting.
        * **threshold** (float, optional): Operational threshold.
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
        r"""
        Updates an existing State Machine definition.

        **Parameters:**

        * **name** (StringType): Machine name.
        * **machine_interval** (IntegerType, optional): New interval.
        * **description** (StringType, optional): New description.
        * **classification** (StringType, optional): New classification.
        * **buffer_size** (IntegerType, optional): New buffer size.
        * **buffer_roll_type** (StringType, optional): New roll type.
        * **criticity** (IntegerType, optional): New criticality.
        * **priority** (IntegerType, optional): New priority.
        * **on_delay** (IntegerType, optional): New on delay.
        * **threshold** (FloatType, optional): New threshold.
        """

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
        r"""
        Retrieves all machine definitions.
        """
        if not self.check_connectivity():

            return list()
        
        return Machines.read_all()
    
    @db_rollback
    def read_config(self):
        r"""
        Retrieves machine configuration for the scheduler.
        """
        if not self.check_connectivity():
            
            return None

        return Machines.read_config()
    
    @db_rollback
    def bind_tag(self, tag:Tag, machine, default_tag_name:str=None):
        r"""
        Binds a Tag to a State Machine in the database.

        **Parameters:**

        * **tag** (Tag): The Tag object.
        * **machine** (StateMachine): The Machine object.
        * **default_tag_name** (str, optional): Default tag alias within the machine.
        """
        if not self.check_connectivity():

            return None
            
        TagsMachines.create(tag_name=tag.name, machine_name=machine.name.value, default_tag_name=default_tag_name)

    @db_rollback
    def unbind_tag(self, tag:Tag, machine):
        r"""
        Unbinds a Tag from a State Machine.
        """
        if not self.check_connectivity():

            return None

        tag_from_db = Tags.get_or_none(name=tag.name)
        machine_from_db= Machines.get_or_none(name=machine.name.value)
        tags_machine = TagsMachines.get((TagsMachines.tag == tag_from_db) & (TagsMachines.machine == machine_from_db))
        tags_machine.delete_instance()    

class MachinesLoggerEngine(BaseEngine):
    r"""
    Thread-safe Engine for the MachinesLogger.
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
        r"""
        Thread-safe machine creation.
        """
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
        r"""
        Thread-safe machine update.
        """
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
        r"""
        Thread-safe read all machines.
        """
        _query = dict()
        _query["action"] = "read_all"
        _query["parameters"] = dict()
        return self.query(_query)
    
    def read_config(self):
        r"""
        Thread-safe read config.
        """
        _query = dict()
        _query["action"] = "read_config"
        _query["parameters"] = dict()
        return self.query(_query)
    
    def bind_tag(self, tag:Tag, machine, default_tag_name:str=None):
        r"""
        Thread-safe bind tag.
        """
        _query = dict()
        _query["action"] = "bind_tag"
        _query["parameters"] = dict()
        _query["parameters"]["tag"] = tag
        _query["parameters"]["machine"] = machine
        _query["parameters"]["default_tag_name"] = default_tag_name
        return self.query(_query)
    
    def unbind_tag(self, tag:Tag, machine):
        r"""
        Thread-safe unbind tag.
        """
        _query = dict()
        _query["action"] = "unbind_tag"
        _query["parameters"] = dict()
        _query["parameters"]["tag"] = tag
        _query["parameters"]["machine"] = machine
        return self.query(_query)
