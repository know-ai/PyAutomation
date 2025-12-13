import pytz
from peewee import CharField, FloatField, ForeignKeyField, TimestampField
from ..dbmodels.core import BaseModel 
from datetime import datetime
from .tags import Tags
from ..alarms.states import States
from ..tags.cvt import CVTEngine
from ..utils.decorators import logging_error_handler

tag_engine = CVTEngine()

class AlarmTypes(BaseModel):
    r"""
    Database model for Alarm Types (e.g., HIGH, LOW, BOOL).
    """

    name = CharField(unique=True)                       # high-high , high , bool , low , low-low

    @classmethod
    @logging_error_handler
    def create(cls, name:str)-> dict:
        r"""
        Creates a new Alarm Type if it doesn't exist.

        **Parameters:**

        * **name** (str): The name of the alarm type (e.g., 'HIGH').

        **Returns:**

        * **dict**: Result dictionary containing status message and data.
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
    @logging_error_handler
    def read_by_name(cls, name:str):
        r"""
        Retrieves an Alarm Type by name.

        **Parameters:**

        * **name** (str): Alarm type name.

        **Returns:**

        * **AlarmTypes**: The model instance or None.
        """        
        return cls.get_or_none(name=name.upper())

    @classmethod
    @logging_error_handler
    def name_exist(cls, name:str)->bool:
        r"""
        Checks if an Alarm Type name exists.

        **Parameters:**

        * **name** (str): Alarm type name.

        **Returns:**

        * **bool**: True if exists.
        """
        query = cls.get_or_none(name=name.upper())
        
        if query is not None:

            return True
        
        return False

    @logging_error_handler
    def serialize(self)-> dict:
        r"""
        Serializes the record to a dictionary.
        """

        return {
            "id": self.id,
            "name": self.name
        }


class AlarmStates(BaseModel):
    r"""
    Database model for Alarm States (ISA 18.2).
    """
    name = CharField(unique=True)
    mnemonic = CharField(max_length=20)
    condition = CharField(max_length=20)
    status = CharField(max_length=20)

    @classmethod
    @logging_error_handler
    def create(cls, name:str, mnemonic:str, condition:str, status:str)-> dict:
        r"""
        Creates a new Alarm State.

        **Parameters:**

        * **name** (str): State name (e.g., 'Unacknowledged').
        * **mnemonic** (str): Short code (e.g., 'UNACK').
        * **condition** (str): Process condition.
        * **status** (str): Status description.

        **Returns:**

        * **AlarmStates**: The created instance or existing one.
        """

        if not cls.name_exist(name):

            query = cls(name=name, mnemonic=mnemonic, condition=condition, status=status)
            query.save()
            
            return query

    @classmethod
    @logging_error_handler
    def read_by_name(cls, name:str):
        r"""
        Retrieves an Alarm State by name.
        """
        return cls.get_or_none(name=name)

    @classmethod
    @logging_error_handler
    def name_exist(cls, name:str)->bool:
        r"""
        Checks if an Alarm State name exists.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    @logging_error_handler
    def serialize(self)-> dict:
        r"""
        Serializes the record.
        """

        return {
            "id": self.id,
            "name": self.name,
            "mnemonic": self.mnemonic,
            "condition": self.condition,
            "status": self.status
        }


class Alarms(BaseModel):
    r"""
    Database model for configured Alarms.
    """
    
    identifier = CharField(unique=True)
    name = CharField(unique=True, max_length=128)
    tag = ForeignKeyField(Tags, backref='alarms')
    trigger_type = ForeignKeyField(AlarmTypes, backref='alarms')
    trigger_value = FloatField()
    description = CharField(null=True, max_length=256)
    state = ForeignKeyField(AlarmStates, backref='alarms')
    timestamp = TimestampField(utc=True, null=True)

    @classmethod
    @logging_error_handler
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
        r"""
        Creates a new Alarm configuration record.

        **Parameters:**

        * **identifier** (str): Unique ID.
        * **name** (str): Alarm name.
        * **tag** (str): Associated Tag name.
        * **trigger_type** (str): Type of trigger.
        * **trigger_value** (float): Threshold value.
        * **description** (str, optional): Description.
        * **state** (str, optional): Initial state.
        * **timestamp** (datetime, optional): Creation timestamp.

        **Returns:**

        * **Alarms**: The created alarm record.
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
    @logging_error_handler
    def name_exists(cls, name:str)->bool|None:
        r"""
        Checks if an alarm name exists.
        """
        tag = cls.get_or_none(name=name)
        if tag:

            return True
        
    @classmethod
    @logging_error_handler
    def read(cls, id:str):
        r"""
        Reads an alarm by ID.
        """
        return cls.get_or_none(id=id)
    
    @classmethod
    @logging_error_handler
    def read_by_identifier(cls, identifier:str):
        r"""
        Reads an alarm by unique identifier.
        """
        return cls.get_or_none(identifier=identifier)
        
    @classmethod
    @logging_error_handler
    def read_by_name(cls, name:str):
        r"""
        Reads an alarm by name.
        """
        return cls.get_or_none(name=name)

    @logging_error_handler
    def serialize(self):
        r"""
        Serializes the alarm record.
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
    r"""
    Database model for Alarm History (Summary).
    """
    
    alarm = ForeignKeyField(Alarms, backref='summary')
    state = ForeignKeyField(AlarmStates, backref='summary')
    alarm_time = TimestampField(utc=True)
    ack_time = TimestampField(utc=True, null=True)

    @classmethod
    @logging_error_handler
    def create(cls, name:str, state:str, timestamp:datetime, ack_timestamp:datetime=None):
        r"""
        Creates a new entry in the alarm summary.

        **Parameters:**

        * **name** (str): Alarm name.
        * **state** (str): Alarm state.
        * **timestamp** (datetime): Time of occurrence.
        * **ack_timestamp** (datetime, optional): Acknowledgment time.
        """
        _alarm = Alarms.read_by_name(name=name)
        _state = AlarmStates.read_by_name(name=state)
        
        if _alarm:

            if _state:

                # Create record
                query = cls(alarm=_alarm.id, state=_state.id, alarm_time=timestamp, ack_time=ack_timestamp)
                query.save()
                
                return query

    @classmethod
    @logging_error_handler
    def read_by_name(cls, name:str):
        r"""
        Retrieves the latest summary entry for a specific alarm name.
        """
        alarm = Alarms.read_by_name(name=name)
        return cls.select().where(cls.alarm==alarm).order_by(cls.id.desc()).get_or_none()

    @classmethod
    @logging_error_handler
    def read_by_alarm_id(cls, alarm_id:int):
        r"""
        Retrieves the latest summary entry by alarm ID.
        """
        alarm = Alarms.read(id=alarm_id)
        return cls.select().where(cls.alarm==alarm).order_by(cls.id.desc()).get_or_none()

    @classmethod
    @logging_error_handler
    def read_all(cls, page:int=1, limit:int=20):
        r"""
        Retrieves alarm summary records with pagination.

        **Parameters:**

        * **page** (int): Page number (default: 1).
        * **limit** (int): Records per page (default: 20).

        **Returns:**

        * **dict**: {data: list, pagination: dict}
        """
        import math
        data = list()
        
        try:
            query = cls.select().order_by(cls.id.desc())
            
            total_records = query.count()
            
            # Safe pagination
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

        except Exception as _err:

            return {
                "data": data,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total_records": 0,
                    "total_pages": 1,
                    "has_next": False,
                    "has_prev": False
                }
            }

    @classmethod
    @logging_error_handler
    def read_lasts(cls, lasts:int=1):
        r"""
        Retrieves the last N records.
        """
        alarms = cls.select().order_by(cls.id.desc()).limit(lasts)

        return [alarm.serialize() for alarm in alarms]
    
    @classmethod
    @logging_error_handler
    def filter_by(
        cls,
        states:list[str]=None,
        names:list[str]=None,
        tags:list[str]=None,
        greater_than_timestamp:datetime=None,
        less_than_timestamp:datetime=None,
        page:int=1,
        limit:int=20
        ):
        r"""
        Filters alarm summary records with pagination.

        **Parameters:**

        * **states** (list[str]): Filter by states.
        * **names** (list[str]): Filter by alarm names.
        * **tags** (list[str]): Filter by tag names.
        * **greater_than_timestamp** (datetime): Start time in UTC (naive or timezone-aware).
        * **less_than_timestamp** (datetime): End time in UTC (naive or timezone-aware).
        * **page**, **limit**: Pagination control.

        **Returns:**

        * **dict**: {data: list, pagination: dict}
        
        **Note:**
        All timestamps are expected to be in UTC. The model always works with UTC.
        Timezone conversions should be handled at the API endpoint level.
        """
        import math
        query = cls.select()
        
        # Only apply filters if the lists are provided and not empty
        # If None or empty list, return all records (no filtering)
        if states and len(states) > 0:
            # Use the ForeignKey relationship directly instead of JOIN
            state_ids = AlarmStates.select(AlarmStates.id).where(AlarmStates.name.in_(states))
            query = query.where(cls.state.in_(state_ids))
        
        if names and len(names) > 0:
            # Use the ForeignKey relationship directly instead of JOIN
            alarm_ids = Alarms.select(Alarms.id).where(Alarms.name.in_(names))
            query = query.where(cls.alarm.in_(alarm_ids))
        
        if tags and len(tags) > 0:
            # Filter by tags: get alarm IDs that have these tags
            tag_ids = Tags.select(Tags.id).where(Tags.name.in_(tags))
            alarm_ids = Alarms.select(Alarms.id).where(Alarms.tag.in_(tag_ids))
            query = query.where(cls.alarm.in_(alarm_ids))
        
        if greater_than_timestamp:
            # Expect datetime object in UTC (already converted by endpoint)
            # If it's timezone-aware, convert to UTC and then to naive
            # If it's naive, assume it's already in UTC
            if isinstance(greater_than_timestamp, datetime):
                if greater_than_timestamp.tzinfo is not None:
                    # Timezone-aware: convert to UTC
                    dt_utc = greater_than_timestamp.astimezone(pytz.UTC)
                    dt_naive = dt_utc.replace(tzinfo=None)
                else:
                    # Naive: assume already in UTC
                    dt_naive = greater_than_timestamp
            else:
                # String: parse and assume UTC
                try:
                    if '.' in str(greater_than_timestamp):
                        parts = str(greater_than_timestamp).split('.')
                        base_time = parts[0]
                        microseconds = parts[1] if len(parts) > 1 else '0'
                        microseconds = microseconds.ljust(6, '0')[:6]
                        formatted_str = f"{base_time}.{microseconds}"
                        dt_naive = datetime.strptime(formatted_str, '%Y-%m-%d %H:%M:%S.%f')
                    else:
                        dt_naive = datetime.strptime(str(greater_than_timestamp), '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    dt = datetime.fromisoformat(str(greater_than_timestamp).replace('Z', '+00:00'))
                    if dt.tzinfo:
                        dt_naive = dt.astimezone(pytz.UTC).replace(tzinfo=None)
                    else:
                        dt_naive = dt
            
            query = query.where(cls.alarm_time > dt_naive)
        
        if less_than_timestamp:
            # Expect datetime object in UTC (already converted by endpoint)
            # If it's timezone-aware, convert to UTC and then to naive
            # If it's naive, assume it's already in UTC
            if isinstance(less_than_timestamp, datetime):
                if less_than_timestamp.tzinfo is not None:
                    # Timezone-aware: convert to UTC
                    dt_utc = less_than_timestamp.astimezone(pytz.UTC)
                    dt_naive = dt_utc.replace(tzinfo=None)
                else:
                    # Naive: assume already in UTC
                    dt_naive = less_than_timestamp
            else:
                # String: parse and assume UTC
                try:
                    if '.' in str(less_than_timestamp):
                        parts = str(less_than_timestamp).split('.')
                        base_time = parts[0]
                        microseconds = parts[1] if len(parts) > 1 else '0'
                        microseconds = microseconds.ljust(6, '0')[:6]
                        formatted_str = f"{base_time}.{microseconds}"
                        dt_naive = datetime.strptime(formatted_str, '%Y-%m-%d %H:%M:%S.%f')
                    else:
                        dt_naive = datetime.strptime(str(less_than_timestamp), '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    dt = datetime.fromisoformat(str(less_than_timestamp).replace('Z', '+00:00'))
                    if dt.tzinfo:
                        dt_naive = dt.astimezone(pytz.UTC).replace(tzinfo=None)
                    else:
                        dt_naive = dt
            
            query = query.where(cls.alarm_time < dt_naive)
        
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
    @logging_error_handler
    def get_alarm_summary_comments(cls, id:int):
        r"""
        Retrieves comments associated with a specific alarm summary entry.
        """
        query = cls.read(id=id)

        return [comment.serialize() for comment in query.logs]

    @logging_error_handler
    def serialize(self):
        r"""
        Serializes the summary record.
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
    