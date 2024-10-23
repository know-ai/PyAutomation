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
        _query = None
        if usernames:
            subquery = Users.select(Users.id).where(Users.username.in_(usernames))
            _query = cls.select().join(Users).where(Users.id.in_(subquery)).order_by(cls.id.desc())

        if event_ids:

            subquery = Events.select(Events.id).where(Events.id.in_(event_ids))
            if _query:
                _query = _query.select().join(Events).where(cls.in_(subquery)).order_by(cls.id.desc())
            else:
                _query = cls.select().join(Events).where(cls.in_(subquery)).order_by(cls.id.desc())

        if alarm_names:
            subquery = Alarms.select(Alarms.id).where(Alarms.name.in_(alarm_names))
            subquery = subquery.select().join(Alarms).where(Alarms.id.in_(subquery)).order_by(AlarmSummary.id.desc())
            if _query:
                _query = _query.select().join(AlarmSummary).where(cls.in_(subquery)).order_by(cls.id.desc())
            else:
                _query = cls.select().join(AlarmSummary).where(cls.in_(subquery)).order_by(cls.id.desc())

        if description:

            if _query:

                _query = _query.select().where(fn.LOWER(cls.description).contains(description.lower()))

            else:

                _query = cls.select().where(fn.LOWER(cls.description).contains(description.lower()))

        if message:

            if _query:

                _query = _query.select().where(fn.LOWER(cls.message).contains(message.lower()))

            else:

                _query = cls.select().where(fn.LOWER(cls.message).contains(message.lower()))

        if classification:

            if _query:

                _query = _query.select().where(fn.LOWER(cls.classification).contains(classification.lower()))

            else:

                _query = cls.select().where(fn.LOWER(cls.classification).contains(classification.lower()))

        if greater_than_timestamp:
            greater_than_timestamp = _timezone.localize(datetime.strptime(greater_than_timestamp, '%Y-%m-%d %H:%M:%S.%f')).astimezone(pytz.UTC).timestamp()
            if _query:

                _query = _query.select().where(cls.timestamp > greater_than_timestamp).order_by(cls.id.desc())

            else:

                _query = cls.select().where(cls.timestamp > greater_than_timestamp).order_by(cls.id.desc())

        if less_than_timestamp:
            less_than_timestamp = _timezone.localize(datetime.strptime(less_than_timestamp, '%Y-%m-%d %H:%M:%S.%f')).astimezone(pytz.UTC).timestamp()
            if _query:

                _query = _query.select().where(cls.timestamp < less_than_timestamp).order_by(cls.id.desc())

            else:

                _query = cls.select().where(cls.timestamp < less_than_timestamp).order_by(cls.id.desc())

        if _query:

            return [event.serialize() for event in _query]
    
        _query = cls.select().order_by(cls.id.desc())
        return [log.serialize() for log in _query]


    def serialize(self)-> dict:

        timestamp = self.timestamp
        if timestamp:

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
            "alarm": _alarm
        }