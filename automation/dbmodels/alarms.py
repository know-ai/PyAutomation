import pytz
from peewee import CharField, FloatField, ForeignKeyField, TimestampField
from ..dbmodels.core import BaseModel 
from datetime import datetime
from .tags import Tags
from ..alarms.states import States
from ..tags.cvt import CVTEngine

tag_engine = CVTEngine()

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
    name = CharField(unique=True, max_length=128)
    tag = ForeignKeyField(Tags, backref='alarms')
    trigger_type = ForeignKeyField(AlarmTypes, backref='alarms')
    trigger_value = FloatField()
    description = CharField(null=True, max_length=256)
    state = ForeignKeyField(AlarmStates, backref='alarms')
    timestamp = TimestampField(utc=True, null=True)

    @classmethod
    def create(
        cls,
        identifier:str,
        name:str,
        tag:str,  
        trigger_type:str,
        trigger_value:float,
        description:str=None,
        state:str=States.NORM.value,
        timestamp:datetime=None
        ):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        trigger_type = AlarmTypes.read_by_name(name=trigger_type)
        tag = Tags.read_by_name(name=tag)
        state = AlarmStates.read_by_name(name=state)
        if not cls.name_exists(name):

            alarm = super().create(
                identifier=identifier,
                name=name,
                tag=tag,  
                trigger_type=trigger_type,
                trigger_value=trigger_value,
                description=description,
                state=state,
                timestamp=timestamp
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
    def read_by_identifier(cls, identifier:str):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        return cls.get_or_none(identifier=identifier)
        
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

            timestamp = timestamp.strftime(tag_engine.DATETIME_FORMAT)

        return {
            'identifier': self.identifier,
            'name': self.name,
            'tag': self.tag.name,  
            'alarm_type': self.trigger_type.name,
            'trigger_value': self.trigger_value,
            'description': self.description,
            'state': self.state.name,
            'timestamp': timestamp
        }
    

class AlarmSummary(BaseModel):
    
    alarm = ForeignKeyField(Alarms, backref='summary')
    state = ForeignKeyField(AlarmStates, backref='summary')
    alarm_time = TimestampField(utc=True)
    ack_time = TimestampField(utc=True, null=True)

    @classmethod
    def create(cls, name:str, state:str, timestamp:datetime, ack_timestamp:datetime=None):
        _alarm = Alarms.read_by_name(name=name)
        _state = AlarmStates.read_by_name(name=state)
        
        if _alarm:

            if _state:

                # Create record
                query = cls(alarm=_alarm.id, state=_state.id, alarm_time=timestamp, ack_time=ack_timestamp)
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
        alarms = cls.select().order_by(cls.id.desc()).limit(lasts)

        return [alarm.serialize() for alarm in alarms]
    
    @classmethod
    def filter_by(
        cls,
        states:list[str]=None,
        names:list[str]=None,
        tags:list[str]=None,
        greater_than_timestamp:datetime=None,
        less_than_timestamp:datetime=None,
        timezone:str='UTC',
        page:int=1,
        limit:int=20
        ):
        r"""
        Documentation here
        """
        import math
        _timezone = pytz.timezone(timezone)
        query = cls.select()
        
        if states:
            subquery = AlarmStates.select(AlarmStates.id).where(AlarmStates.name.in_(states))
            query = query.join(AlarmStates).where(AlarmStates.id.in_(subquery))
        
        if names:
            subquery = Alarms.select(Alarms.id).where(Alarms.name.in_(names))
            query = query.join(Alarms).where(Alarms.id.in_(subquery))
        
        if tags:
            subquery = Tags.select(Tags.id).where(Tags.name.in_(tags))
            subquery = Alarms.select(Alarms.id).join(Tags).where(Tags.id.in_(subquery))
            query = query.join(Alarms).where(Alarms.id.in_(subquery))
        
        if greater_than_timestamp:
            greater_than_timestamp = _timezone.localize(datetime.strptime(greater_than_timestamp, '%Y-%m-%d %H:%M:%S.%f')).astimezone(pytz.UTC)
            query = query.where(cls.alarm_time > greater_than_timestamp)
        
        if less_than_timestamp:
            less_than_timestamp = _timezone.localize(datetime.strptime(less_than_timestamp, '%Y-%m-%d %H:%M:%S.%f')).astimezone(pytz.UTC)
            query = query.where(cls.alarm_time < less_than_timestamp)
        
        query = query.order_by(cls.id.desc())
        
        total_records = query.count()
        
        if limit <= 0: limit = 20
        if page <= 0: page = 1
        
        total_pages = math.ceil(total_records / limit)
        if total_pages == 0: total_pages = 1
        
        has_next = page < total_pages
        has_prev = page > 1
        
        paginated_query = query.paginate(page, limit)
        
        data = [alarm.serialize() for alarm in paginated_query]
        
        return {
            "data": data,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_records": total_records,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev
            }
        }

    @classmethod
    def get_alarm_summary_comments(cls, id:int):
        r"""
        Documentation here
        """
        query = cls.read(id=id)

        return [comment.serialize() for comment in query.logs]

    def serialize(self):
        r"""
        Documentation here
        """
        from .. import TIMEZONE

        ack_time = None
        if self.ack_time:
            ack_time = self.ack_time
            ack_time = pytz.UTC.localize(ack_time).astimezone(TIMEZONE)
            ack_time = ack_time.strftime(tag_engine.DATETIME_FORMAT)

        alarm_time = self.alarm_time
        alarm_time = pytz.UTC.localize(alarm_time).astimezone(TIMEZONE)
        alarm_time = alarm_time.strftime(tag_engine.DATETIME_FORMAT)

        return {
            'id': self.id,
            'name': self.alarm.name,
            'tag': self.alarm.tag.name,
            'description': self.alarm.description,
            'state': self.state.name,
            'mnemonic': self.state.mnemonic,
            'status': self.state.status,
            'alarm_time': alarm_time,
            'ack_time': ack_time,
            'has_comments': True if self.logs else False
        }
    