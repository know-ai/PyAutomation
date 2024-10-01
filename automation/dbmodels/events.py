from peewee import CharField, DateTimeField, ForeignKeyField, IntegerField
from ..dbmodels.core import BaseModel
from datetime import datetime
from .users import Users
from ..modules.users.users import User

DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"


class Events(BaseModel):

    timestamp = DateTimeField()
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
        less_than_timestamp:datetime=None):
        r"""
        Documentation here
        """
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

        if greater_than_timestamp:
            
            if _query:

                _query = _query.select().where(cls.timestamp > greater_than_timestamp).order_by(cls.id.desc())

            else:

                _query = cls.select().where(cls.timestamp > greater_than_timestamp).order_by(cls.id.desc())

        if less_than_timestamp:
            
            if _query:

                _query = _query.select().where(cls.timestamp < less_than_timestamp).order_by(cls.id.desc())

            else:

                _query = cls.select().where(cls.timestamp < less_than_timestamp).order_by(cls.id.desc())


        return [event.serialize() for event in _query]
    
    @classmethod
    def get_comments(cls, id:int):
        r"""
        Documentation here
        """
        query = cls.read(id=id)

        return [comment.serialize() for comment in query.logs]

    def serialize(self)-> dict:

        timestamp = self.timestamp
        if timestamp:

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
    

