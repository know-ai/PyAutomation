import pytz
from peewee import CharField, TimestampField, ForeignKeyField, IntegerField, fn
from ..dbmodels.core import BaseModel
from datetime import datetime
from .users import Users
from ..modules.users.users import User

DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"


class Events(BaseModel):

    timestamp = TimestampField(utc=True)
    message = CharField(max_length=256)
    description = CharField(max_length=256, null=True)
    classification = CharField(max_length=128, null=True)
    priority = IntegerField(null=True)
    criticity = IntegerField(null=True)
    user = ForeignKeyField(Users, backref='events', on_delete='CASCADE')

    @classmethod
    def create(
        cls, 
        message:str, 
        user:User, 
        description:str=None, 
        classification:str=None,
        priority:int=None,
        criticity:int=None,
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
            priority=priority,
            criticity=criticity,
            timestamp=timestamp
        )
        query.save()

        return query, f"Event creation successful"
    
    @classmethod
    def read_lasts(cls, lasts:int=1):
        r"""
        Documentation here
        """
        events = cls.select().order_by(cls.id.desc()).limit(lasts)

        return [event.serialize() for event in events]
    
    @classmethod
    def filter_by(
        cls, 
        usernames:list[str]=None,
        priorities:list[int]=None,
        criticities:list[int]=None,
        greater_than_timestamp:datetime=None,
        less_than_timestamp:datetime=None,
        description:str="",
        message:str="",
        classification:str="",
        timezone:str='UTC'):
        r"""
        Documentation here
        """
        _timezone = pytz.timezone(timezone) 
        _query = None
        if usernames:
            
            subquery = Users.select(Users.id).where(Users.username.in_(usernames))
            _query = cls.select().join(Users).where(Users.id.in_(subquery)).order_by(cls.id.desc())

        if priorities:

            if _query:

                _query = _query.select().where(cls.in_(priorities)).order_by(cls.id.desc())

            else:
                _query = cls.select().where(cls.in_(priorities)).order_by(cls.id.desc())

        if criticities:

            if _query:

                _query = _query.select().where(cls.in_(criticities)).order_by(cls.id.desc())

            else:
                _query = cls.select().where(cls.in_(criticities)).order_by(cls.id.desc())

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
        return [event.serialize() for event in _query]
    
    @classmethod
    def get_comments(cls, id:int):
        r"""
        Documentation here
        """
        query = cls.read(id=id)

        return [comment.serialize() for comment in query.logs]

    def serialize(self)-> dict:
        from .. import TIMEZONE
        timestamp = self.timestamp
        if timestamp:

            timestamp = pytz.UTC.localize(timestamp).astimezone(TIMEZONE)
            timestamp = timestamp.strftime(DATETIME_FORMAT)

        return {
            "id": self.id,
            "timestamp": timestamp,
            "user": self.user.serialize(),
            "message": self.message,
            "description": self.description,
            "classification": self.classification,
            "priority": self.priority,
            "criticity": self.criticity
        }
    

