from peewee import CharField, DateTimeField, ForeignKeyField, IntegerField
from automation.dbmodels.core import BaseModel
from datetime import datetime
from .users import Users
from automation.modules.users.users import User
from ..tags.cvt import CVTEngine

tag_engine = CVTEngine()


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

    def serialize(self)-> dict:

        timestamp = self.timestamp
        if timestamp:

            timestamp = timestamp.strftime(tag_engine.DATETIME_FORMAT)

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