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

            timestamp = datetime.now(pytz.UTC)
        
        if not isinstance(timestamp, datetime):

            return None, f"Timestamp must be a datetime Object"
        
        # Ensure timestamp is timezone-aware and in UTC
        if timestamp.tzinfo is None:
            # If naive, assume it's UTC
            timestamp = pytz.UTC.localize(timestamp)
        else:
            # If timezone-aware, convert to UTC
            timestamp = timestamp.astimezone(pytz.UTC)
        
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
            # If it's already a datetime object (naive UTC from endpoint), use it directly
            if isinstance(greater_than_timestamp, datetime):
                if greater_than_timestamp.tzinfo is not None:
                    # Convert to naive UTC
                    dt_utc = greater_than_timestamp.astimezone(pytz.UTC)
                    greater_than_timestamp = dt_utc.replace(tzinfo=None)
            else:
                # Legacy: parse string and convert from user timezone to UTC
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
                    dt_local = _timezone.localize(dt_naive)
                    dt_utc = dt_local.astimezone(pytz.UTC)
                    greater_than_timestamp = dt_utc.replace(tzinfo=None)
                except ValueError:
                    # Try ISO format as fallback
                    dt = datetime.fromisoformat(str(greater_than_timestamp).replace('Z', '+00:00'))
                    if dt.tzinfo is not None:
                        dt = dt.astimezone(pytz.UTC)
                    greater_than_timestamp = dt.replace(tzinfo=None)
            
            query = query.where(cls.timestamp > greater_than_timestamp)
        
        if less_than_timestamp:
            # If it's already a datetime object (naive UTC from endpoint), use it directly
            if isinstance(less_than_timestamp, datetime):
                if less_than_timestamp.tzinfo is not None:
                    # Convert to naive UTC
                    dt_utc = less_than_timestamp.astimezone(pytz.UTC)
                    less_than_timestamp = dt_utc.replace(tzinfo=None)
            else:
                # Legacy: parse string and convert from user timezone to UTC
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
                    dt_local = _timezone.localize(dt_naive)
                    dt_utc = dt_local.astimezone(pytz.UTC)
                    less_than_timestamp = dt_utc.replace(tzinfo=None)
                except ValueError:
                    # Try ISO format as fallback
                    dt = datetime.fromisoformat(str(less_than_timestamp).replace('Z', '+00:00'))
                    if dt.tzinfo is not None:
                        dt = dt.astimezone(pytz.UTC)
                    less_than_timestamp = dt.replace(tzinfo=None)
            
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
        
        # Serialize logs with the specified timezone
        data = [log.serialize(timezone=timezone) for log in paginated_query]
        
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

    def serialize(self, timezone=None)-> dict:
        r"""
        Serializes the log record.
        
        **Parameters:**
        
        * **timezone** (str, optional): Timezone to convert timestamp to. If None, uses default TIMEZONE.
        """
        from .. import MANUFACTURER, SEGMENT, TIMEZONE
        timestamp = self.timestamp
        if timestamp:
            # Convert to specified timezone or default TIMEZONE
            target_tz = pytz.timezone(timezone) if timezone else TIMEZONE
            # If timestamp is naive, assume it's UTC
            if timestamp.tzinfo is None:
                timestamp = pytz.UTC.localize(timestamp)
            timestamp = timestamp.astimezone(target_tz)
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