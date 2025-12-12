import pytz
from peewee import CharField, TimestampField, ForeignKeyField, fn
from ..dbmodels.core import BaseModel
from datetime import datetime
from .users import Users
from .events import Events
from .alarms import AlarmSummary, Alarms
from ..modules.users.users import User

DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"


class Logs(BaseModel):
    r"""
    Database model for Application Logs.

    Logs store system messages, errors, and informational records, optionally linked to
    events or alarms.
    """
    
    timestamp = TimestampField(utc=True)
    message = CharField(max_length=256)
    description = CharField(max_length=256, null=True)
    classification = CharField(max_length=128, null=True)
    user = ForeignKeyField(Users, backref='logs', on_delete='CASCADE')
    alarm = ForeignKeyField(AlarmSummary, null=True, backref='logs', on_delete='CASCADE')
    event = ForeignKeyField(Events, null=True, backref='logs', on_delete='CASCADE')

    @classmethod
    def create(
        cls, 
        message:str, 
        user:User, 
        description:str=None, 
        classification:str=None,
        alarm_summary_id:int=None,
        event_id:int=None,
        timestamp:datetime=None
        )->tuple:
        r"""
        Creates a new log entry.

        **Parameters:**

        * **message** (str): Log content.
        * **user** (User): User creating the log.
        * **description** (str, optional): Additional details.
        * **classification** (str, optional): Log type/category.
        * **alarm_summary_id** (int, optional): Link to an alarm summary entry.
        * **event_id** (int, optional): Link to an event.
        * **timestamp** (datetime, optional): Log time.

        **Returns:**

        * **tuple**: (Query object, status message)
        """
        if not isinstance(user, User):

            return None, f"User {user} - {type(user)} must be an User Object"
        
        _user = Users.read_by_username(username=user.username) 

        if not timestamp:

            timestamp = datetime.now()
        
        if not isinstance(timestamp, datetime):

            return None, f"Timestamp must be a datetime Object"
        
        query = cls(
            message=message,
            user=_user,
            description=description,
            classification=classification,
            timestamp=timestamp,
            event=Events.get_or_none(id=event_id),
            alarm=AlarmSummary.get_or_none(id=alarm_summary_id)
        )
        query.save()

        return query, f"Event creation successful"
    
    @classmethod
    def read_lasts(cls, lasts:int=1):
        r"""
        Retrieves the last N logs.

        **Parameters:**

        * **lasts** (int): Number of logs to retrieve.

        **Returns:**

        * **list**: List of serialized log dictionaries.
        """
        logs = cls.select().order_by(cls.id.desc()).limit(lasts)

        return [log.serialize() for log in logs]
    
    @classmethod
    def filter_by(
        cls, 
        usernames:list[str]=None,
        alarm_names:list[str]=None,
        event_ids:list[int]=None,
        description:str="",
        message:str="",
        classification:str="",
        greater_than_timestamp:datetime=None,
        less_than_timestamp:datetime=None,
        timezone:str='UTC',
        page:int=1,
        limit:int=20
        ):
        r"""
        Filters logs based on various criteria with pagination.

        **Parameters:**

        * **usernames** (list[str]): Filter by user.
        * **alarm_names** (list[str]): Filter by linked alarm name.
        * **event_ids** (list[int]): Filter by linked event ID.
        * **message**, **description**, **classification**: Text search.
        * **greater_than_timestamp**, **less_than_timestamp**: Time range.
        * **page**, **limit**: Pagination control.

        **Returns:**

        * **dict**: {data: list, pagination: dict}
        """
        import math
        _timezone = pytz.timezone(timezone)
        query = cls.select()
        
        if usernames:
            subquery = Users.select(Users.id).where(Users.username.in_(usernames))
            query = query.join(Users).where(Users.id.in_(subquery))
        
        if event_ids:
            subquery = Events.select(Events.id).where(Events.id.in_(event_ids))
            query = query.join(Events).where(Events.id.in_(subquery))
        
        if alarm_names:
            subquery = Alarms.select(Alarms.id).where(Alarms.name.in_(alarm_names))
            alarm_subquery = AlarmSummary.select(AlarmSummary.id).join(Alarms).where(Alarms.id.in_(subquery))
            query = query.join(AlarmSummary).where(AlarmSummary.id.in_(alarm_subquery))
        
        if description:
            query = query.where(fn.LOWER(cls.description).contains(description.lower()))
        
        if message:
            query = query.where(fn.LOWER(cls.message).contains(message.lower()))
        
        if classification:
            query = query.where(fn.LOWER(cls.classification).contains(classification.lower()))
        
        if greater_than_timestamp:
            greater_than_timestamp = _timezone.localize(datetime.strptime(greater_than_timestamp, '%Y-%m-%d %H:%M:%S.%f')).astimezone(pytz.UTC)
            query = query.where(cls.timestamp > greater_than_timestamp)
        
        if less_than_timestamp:
            less_than_timestamp = _timezone.localize(datetime.strptime(less_than_timestamp, '%Y-%m-%d %H:%M:%S.%f')).astimezone(pytz.UTC)
            query = query.where(cls.timestamp < less_than_timestamp)
        
        query = query.order_by(cls.id.desc())

        total_records = query.count()
        
        if limit <= 0: limit = 20
        if page <= 0: page = 1
        
        total_pages = math.ceil(total_records / limit)
        if total_pages == 0: total_pages = 1
        
        has_next = page < total_pages
        has_prev = page > 1
        
        paginated_query = query.paginate(page, limit)
        
        data = [log.serialize() for log in paginated_query]
        
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

    def serialize(self)-> dict:
        r"""
        Serializes the log record.
        """
        from .. import MANUFACTURER, SEGMENT, TIMEZONE
        timestamp = self.timestamp
        if timestamp:
            timestamp = pytz.UTC.localize(timestamp).astimezone(TIMEZONE)
            timestamp = timestamp.strftime(DATETIME_FORMAT)

        _event = None
        if self.event:

            _event = self.event.serialize()

        _alarm = None
        if self.alarm:

            _alarm = self.alarm.serialize()

        return {
            "id": self.id,
            "timestamp": timestamp,
            "user": self.user.serialize(),
            "message": self.message,
            "description": self.description,
            "classification": self.classification,
            "event": _event,
            "alarm": _alarm,
            "segment": SEGMENT,
            "manufacturer": MANUFACTURER
        }