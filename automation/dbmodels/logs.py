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
        Documentation here
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
        timezone:str='UTC'
        ):
        r"""
        Documentation here
        """
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

        if not query.exists():
            
            return []
        
        return [log.serialize() for log in query]

    def serialize(self)-> dict:
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