from peewee import CharField, FloatField, DateTimeField, ForeignKeyField, BooleanField
from automation.dbmodels.core import BaseModel
from datetime import datetime
from .tags import Tags
from ..alarms.states import States

DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"

class AlarmTypes(BaseModel):

    name = CharField(unique=True)                       # high-high , high , bool , low , low-low

    @classmethod
    def create(cls, name:str)-> dict:
        r"""
        You can use Model.create() to create a new model instance. This method accepts keyword arguments, where the keys correspond 
        to the names of the model's fields. A new instance is returned and a row is added to the table.

        ```python
        >>> AlarmsType.create(name='High-High')
        {
            'message': (str)
            'data': (dict) {
                'name': 'HIGH-HIGH'
            }
        }
        ```
        
        This will INSERT a new row into the database. The primary key will automatically be retrieved and stored on the model instance.

        **Parameters**

        * **name:** (str), Industrial protocol name

        **Returns**

        * **result:** (dict) --> {'message': (str), 'data': (dict) row serialized}

        """
        result = dict()
        data = dict()
        name = name.upper()

        if not cls.name_exist(name):

            query = cls(name=name)
            query.save()
            
            message = f"Alarm type {name} created successfully"
            data.update(query.serialize())

            result.update(
                {
                    'message': message, 
                    'data': data
                }
            )
            return result

        message = f"Alarm type {name} is already into database"
        result.update(
            {
                'message': message, 
                'data': data
            }
        )
        return result

    @classmethod
    def read_by_name(cls, name:str):
        r"""
        Get instance by its a name

        **Parameters**

        * **name:** (str) Alarm type name

        **Returns**

        * **bool:** If True, name exist into database 
        """        
        return cls.get_or_none(name=name.upper())

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Verify is a name exist into database

        **Parameters**

        * **name:** (str) Alarm type name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(name=name.upper())
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serialize database record to a jsonable object
        """

        return {
            "id": self.id,
            "name": self.name
        }


class AlarmStates(BaseModel):
    r"""
    Based on ISA 18.2
    """

    name = CharField(unique=True)
    mnemonic = CharField(max_length=20)
    condition = CharField(max_length=20)
    status = CharField(max_length=20)

    @classmethod
    def create(cls, name:str, mnemonic:str, condition:str, status:str)-> dict:
        r"""
        You can use Model.create() to create a new model instance. This method accepts keyword arguments, where the keys correspond 
        to the names of the model's fields. A new instance is returned and a row is added to the table.

        ```python
        >>> AlarmsType.create(name='Unacknowledged', mnemonic='UNACKED', description='Alarm unacknowledged')
        {
            'message': (str)
            'data': (dict) {
                'id': 1,
                'name': 'unacknowledged',
                'mnemonic': 'UNACKED',
                'description': 'Alarm unacknowledged'
            }
        }
        ```
        
        This will INSERT a new row into the database. The primary key will automatically be retrieved and stored on the model instance.

        **Parameters**

        * **name:** (str), Industrial protocol name

        **Returns**

        * **result:** (dict) --> {'message': (str), 'data': (dict) row serialized}

        """

        if not cls.name_exist(name):

            query = cls(name=name, mnemonic=mnemonic, condition=condition, status=status)
            query.save()
            
            return query

    @classmethod
    def read_by_name(cls, name:str)->bool:
        r"""
        Get instance by its a name

        **Parameters**

        * **name:** (str) Alarm type name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        return cls.get_or_none(name=name)

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Verify is a name exist into database

        **Parameters**

        * **name:** (str) Alarm type name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serialize database record to a jsonable object
        """

        return {
            "id": self.id,
            "name": self.name,
            "mnemonic": self.mnemonic,
            "condition": self.condition,
            "status": self.status
        }


class Alarms(BaseModel):

    identifier = CharField(unique=True)
    name = CharField(unique=True, max_length=64)
    tag = ForeignKeyField(Tags, backref='alarms', on_delete='CASCADE')
    trigger_type = ForeignKeyField(AlarmTypes, backref='alarms', on_delete='CASCADE')
    trigger_value = FloatField()
    description = CharField(null=True, max_length=256)
    tag_alarm = CharField(null=True, max_length=64)
    state = ForeignKeyField(AlarmStates, backref='alarms', on_delete='CASCADE')
    timestamp = DateTimeField(null=True)
    acknowledged_timestamp = DateTimeField(null=True)

    @classmethod
    def create(
        cls,
        identifier:str,
        name:str,
        tag:str,  
        trigger_type:str,
        trigger_value:float,
        description:str=None,
        tag_alarm:str=None,
        state:str=States.NORM.value,
        timestamp:datetime=None,
        acknowledged_timestamp:datetime=None
        ):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        if not cls.name_exists(name):

            trigger_type = AlarmTypes.read_by_name(name=trigger_type)
            tag = Tags.read_by_name(name=tag)
            state = AlarmStates.read_by_name(name=state)
            alarm = super().create(
                identifier=identifier,
                name=name,
                tag=tag,  
                trigger_type=trigger_type,
                trigger_value=trigger_value,
                description=description,
                tag_alarm=tag_alarm,
                state=state,
                timestamp=timestamp,
                acknowledged_timestamp=acknowledged_timestamp
            )
            alarm.save()
            return alarm
    
    @classmethod
    def name_exists(cls, name:str)->bool|None:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        tag = cls.get_or_none(name=name)
        if tag:

            return True
        
    @classmethod
    def read(cls, id:str):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        return cls.get_or_none(id=id)
        
    @classmethod
    def read_by_name(cls, name:str):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        return cls.get_or_none(name=name)

    def serialize(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        timestamp = self.timestamp
        if timestamp:

            timestamp = timestamp.strftime(DATETIME_FORMAT)

        acknowledged_timestamp = self.acknowledged_timestamp
        if acknowledged_timestamp:

            acknowledged_timestamp = timestamp.strftime(DATETIME_FORMAT)

        return {
            'identifier': self.identifier,
            'name': self.name,
            'tag': self.tag.name,  
            'type': self.trigger_type.name,
            'trigger_value': self.trigger_value,
            'description': self.description,
            'tag_alarm': self.tag_alarm,
            'state': self.state.name,
            'timestamp': timestamp,
            'acknowledged_timestamp': acknowledged_timestamp
        }
    

class AlarmSummary(BaseModel):
    
    alarm = ForeignKeyField(Alarms, backref='summary', on_delete='CASCADE')
    state = ForeignKeyField(AlarmStates, backref='summary', on_delete='CASCADE')
    alarm_time = DateTimeField(default=datetime.now)
    ack_time = DateTimeField(null=True)
    out_of_service_time = DateTimeField(null=True)
    return_to_service_time = DateTimeField(null=True)
    active = BooleanField(default=True)

    @classmethod
    def create(cls, name:str, state:str):
        _alarm = Alarms.read_by_name(name=name)
        _state = AlarmStates.read_by_name(name=state)

        if _alarm:

            if _state:
            
                # Set Active old alarms False
                old_query = cls.select().where(cls.alarm==_alarm)
                if old_query:
                    
                    for _query in old_query:
                        _query.active = False
                        _query.save()


                # Create record
                query = cls(alarm=_alarm.id, state=_state.id)
                query.save()
                
                return query

    @classmethod
    def read_by_name(cls, name:str)->bool:
        r"""
        Get instance by its a name

        **Parameters**

        * **name:** (str) Alarm type name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        alarm = Alarms.read_by_name(name=name)
        return cls.select().where(cls.alarm==alarm).order_by(cls.id.desc()).get_or_none()

    @classmethod
    def read_by_alarm_id(cls, alarm_id:int)->bool:
        r"""
        Get instance by its a name

        **Parameters**

        * **name:** (str) Alarm type name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        alarm = Alarms.read(id=alarm_id)
        return cls.select().where(cls.alarm==alarm).order_by(cls.id.desc()).get_or_none()

    @classmethod
    def read_all(cls):
        r"""
        Select all records

        You can use this method to retrieve all instances matching in the database. 

        This method is a shortcut that calls Model.select() with the given query.

        **Parameters**

        **Returns**

        * **result:** (dict) --> {'message': (str), 'data': (list) row serialized}
        """

        # result = dict()
        data = list()
        
        try:
            data = [query.serialize() for query in cls.select().order_by(cls.id.desc())]

            return data

        except Exception as _err:

            return data

    @classmethod
    def read_lasts(cls, lasts:int=1):
        r"""
        Documentation here
        """
        alarms = cls.select().where(cls.id > cls.select().count() - int(lasts)).order_by(cls.id.desc())

        result = [alarm.serialize() for alarm in alarms]

        return result

    def serialize(self):
        r"""
        Documentation here
        """
        

        return {
            # 'id': self.id,
            # 'alarm_id': alarm._id,
            # 'name': self.alarm.name,
            # 'state': self.state.name,
            # 'mnemonic': self.state.mnemonic,
            # 'status': self.state.status,
            # 'condition': self.state.condition,
            # 'description': self.alarm.description,
            # 'alarm_time': self.alarm_time.strftime(DATETIME_FORMAT),
            # 'ack_time': ack_time,
            # 'out_of_service_time': out_of_service_time,
            # 'return_to_service_time': return_to_service_time,
            # 'active': self.active,
            # 'audible': alarm.audible,
            # 'is_process_alarm': is_process_alarm,
            # 'comments': self.get_comments()
        }