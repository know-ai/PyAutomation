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
import logging


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
            threshold:float=None,
            area:str=None,
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
            threshold=threshold,
            area=area,
        )
        try:
            from ..catalog.bootstrap import mirror_historian_row

            row = Machines.get_or_none(Machines.name == name) or Machines.get_or_none(
                Machines.identifier == identifier
            )
            if row is not None:
                mirror_historian_row(row)
        except Exception:
            logging.getLogger("pyautomation").debug("catalog machine mirror skipped", exc_info=True)

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
        threshold:FloatType=None,
        execution_interval:float=None,
        sample_interval=None,
        sample_interval_set:bool=False,
        ):
        r"""
        Updates an existing State Machine definition.

        Always mirrors into the local catalog so HMI attribute edits work offline.
        Historian writes are best-effort when connectivity is available.
        """

        def _unwrap(value):
            if value is None:
                return None
            if hasattr(value, "value"):
                inner = value.value
                if hasattr(inner, "value"):
                    return inner.value
                return inner
            return value

        machine_name = name.value if hasattr(name, "value") else name
        fields = {}
        if machine_interval is not None:
            interval = float(_unwrap(machine_interval))
            fields["interval"] = interval
            fields["execution_interval"] = interval
        if execution_interval is not None:
            fields["execution_interval"] = float(execution_interval)
            fields["interval"] = float(execution_interval)
        if sample_interval_set:
            fields["sample_interval"] = sample_interval
        if description is not None:
            fields["description"] = _unwrap(description)
        if classification is not None:
            fields["classification"] = _unwrap(classification)
        if buffer_size is not None:
            fields["buffer_size"] = _unwrap(buffer_size)
        if buffer_roll_type is not None:
            fields["buffer_roll_type"] = _unwrap(buffer_roll_type)
        if criticity is not None:
            fields["criticity"] = _unwrap(criticity)
        if priority is not None:
            fields["priority"] = _unwrap(priority)
        if on_delay is not None:
            fields["on_delay"] = _unwrap(on_delay)
        if threshold is not None:
            fields["threshold"] = _unwrap(threshold)

        local_ok = False
        if fields:
            try:
                from ..catalog.mutations import persist_machine_fields_local

                local_ok = bool(persist_machine_fields_local(name=str(machine_name), **fields))
            except Exception:
                logging.getLogger("pyautomation").debug(
                    "local catalog machine put skipped", exc_info=True
                )

        if not self.check_connectivity():
            return {"message": "updated local catalog", "data": fields} if local_ok or fields else None

        try:
            machine = Machines.read_by_name(name=str(machine_name))
            if machine is None:
                return {"message": "updated local catalog", "data": fields} if local_ok else None
            query = Machines.put(id=machine.id, **fields)
            try:
                from ..catalog.bootstrap import mirror_historian_row

                refreshed = Machines.read_by_name(name=str(machine_name))
                if refreshed is not None:
                    mirror_historian_row(refreshed)
            except Exception:
                logging.getLogger("pyautomation").debug(
                    "catalog machine put mirror skipped", exc_info=True
                )
            return query
        except Exception:
            logging.getLogger("pyautomation").warning(
                "historian machine put failed; local catalog retained name=%s",
                machine_name,
                exc_info=True,
            )
            return {"message": "updated local catalog (historian unreachable)", "data": fields}
    
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
            try:
                from ..catalog.mutations import persist_tagsmachines_bind

                persist_tagsmachines_bind(
                    tag_name=tag.name,
                    machine_name=machine.name.value,
                    default_tag_name=default_tag_name,
                )
            except Exception:
                logging.getLogger("pyautomation").debug(
                    "local catalog tagsmachines bind skipped", exc_info=True
                )
            return None
            
        TagsMachines.create(tag_name=tag.name, machine_name=machine.name.value, default_tag_name=default_tag_name)
        try:
            from ..catalog.mutations import persist_tagsmachines_bind

            persist_tagsmachines_bind(
                tag_name=tag.name,
                machine_name=machine.name.value,
                default_tag_name=default_tag_name,
            )
        except Exception:
            logging.getLogger("pyautomation").debug(
                "catalog tagsmachines bind mirror skipped", exc_info=True
            )

    @db_rollback
    def unbind_tag(self, tag:Tag, machine):
        r"""
        Unbinds a Tag from a State Machine.
        """
        if not self.check_connectivity():
            try:
                from ..catalog.mutations import persist_tagsmachines_unbind

                persist_tagsmachines_unbind(tag_name=tag.name, machine_name=machine.name.value)
            except Exception:
                logging.getLogger("pyautomation").debug(
                    "local catalog tagsmachines unbind skipped", exc_info=True
                )
            return None

        tag_from_db = Tags.get_or_none(name=tag.name)
        machine_from_db= Machines.get_or_none(name=machine.name.value)
        tags_machine = TagsMachines.get((TagsMachines.tag == tag_from_db) & (TagsMachines.machine == machine_from_db))
        tags_machine.delete_instance()
        try:
            from ..catalog.mutations import persist_tagsmachines_unbind

            persist_tagsmachines_unbind(tag_name=tag.name, machine_name=machine.name.value)
        except Exception:
            logging.getLogger("pyautomation").debug(
                "catalog tagsmachines unbind mirror skipped", exc_info=True
            )

    @db_rollback
    def put_sample_override(self, tag:Tag, machine, sample_override):
        if not self.check_connectivity():
            try:
                from ..catalog.mutations import persist_tagsmachines_sample_override

                persist_tagsmachines_sample_override(
                    tag_name=tag.name,
                    machine_name=machine.name.value,
                    sample_override=sample_override,
                )
            except Exception:
                logging.getLogger("pyautomation").debug(
                    "local catalog tagsmachines sample_override skipped", exc_info=True
                )
            return None
        row = TagsMachines.put_sample_override(
            tag_name=tag.name,
            machine_name=machine.name.value,
            sample_override=sample_override,
        )
        try:
            from ..catalog.mutations import persist_tagsmachines_sample_override

            persist_tagsmachines_sample_override(
                tag_name=tag.name,
                machine_name=machine.name.value,
                sample_override=sample_override,
            )
        except Exception:
            logging.getLogger("pyautomation").debug(
                "catalog tagsmachines sample_override mirror skipped", exc_info=True
            )
        return row

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
        threshold:float=None,
        area:str=None,
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
        _query["parameters"]["area"] = area
        
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
        threshold:FloatType=None,
        execution_interval:float=None,
        sample_interval=None,
        sample_interval_set:bool=False,
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
        _query["parameters"]["execution_interval"] = execution_interval
        _query["parameters"]["sample_interval"] = sample_interval
        _query["parameters"]["sample_interval_set"] = sample_interval_set

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

    def put_sample_override(self, tag:Tag, machine, sample_override):
        _query = dict()
        _query["action"] = "put_sample_override"
        _query["parameters"] = dict()
        _query["parameters"]["tag"] = tag
        _query["parameters"]["machine"] = machine
        _query["parameters"]["sample_override"] = sample_override
        return self.query(_query)
