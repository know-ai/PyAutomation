import pytz
from peewee import CharField, TimestampField, ForeignKeyField, IntegerField, fn
from ..dbmodels.core import BaseModel
from datetime import datetime
from .users import Users
from ..modules.users.users import User

DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"


class Events(BaseModel):
    r"""
    Database model for System Events.

    Events track user actions and system changes.
    """
    
    timestamp = TimestampField(utc=True)
    message = CharField(max_length=256)
    description = CharField(max_length=256, null=True)
    classification = CharField(max_length=128, null=True)
    priority = IntegerField(null=True)
    criticity = IntegerField(null=True)
    user = ForeignKeyField(Users, backref='events')

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
        r"""
        Creates a new event record.

        **Parameters:**

        * **message** (str): Event message.
        * **user** (User): User associated with the event.
        * **description** (str, optional): Detailed description.
        * **classification** (str, optional): Event category.
        * **priority** (int, optional): Priority level.
        * **criticity** (int, optional): Criticity level.
        * **timestamp** (datetime, optional): Time of event.

        **Returns:**

        * **tuple**: (Query object, status message)
        """

        if not isinstance(user, User):

            return None, f"User {user} - {type(user)} must be an User Object"
        
        user = Users.read_by_username(username=user.username) 

        if not timestamp:

            timestamp = datetime.now(pytz.UTC)
        
        if not isinstance(timestamp, datetime):

            return None, f"Timestamp must be a datetime Object"

        query = cls(
            message=message,
            user=user,
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
        Retrieves the last N events.

        **Parameters:**

        * **lasts** (int): Number of events to retrieve.

        **Returns:**

        * **list**: List of serialized event dictionaries.
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
        timezone:str='UTC',
        page:int=1,
        limit:int=20
        ):
        r"""
        Filters events based on criteria with pagination.

        **Parameters:**

        * **usernames** (list[str]): Filter by user.
        * **priorities** (list[int]): Filter by priority.
        * **criticities** (list[int]): Filter by criticity.
        * **message**, **description**, **classification**: Text search.
        * **greater_than_timestamp**, **less_than_timestamp**: Time range.
        * **page**, **limit**: Pagination.

        **Returns:**

        * **dict**: {data: list, pagination: dict}
        """
        import math
        _timezone = pytz.timezone(timezone)
        query = cls.select()
        
        if usernames:
            subquery = Users.select(Users.id).where(Users.username.in_(usernames))
            query = query.join(Users).where(Users.id.in_(subquery))
        
        if priorities:
            query = query.where(cls.priority.in_(priorities))
            
        if criticities:
            query = query.where(cls.criticity.in_(criticities))
            
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
        
        data = [event.serialize() for event in paginated_query]
        
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
    def get_comments(cls, id:int):
        r"""
        Retrieves comments (logs) associated with an event.
        """
        query = cls.read(id=id)

        return [comment.serialize() for comment in query.logs]

    def serialize(self)-> dict:
        r"""
        Serializes the event record.
        """
        from .. import TIMEZONE, MANUFACTURER, SEGMENT
        timestamp = self.timestamp
        if timestamp:

            timestamp = timestamp.astimezone(TIMEZONE)
            timestamp = timestamp.strftime(DATETIME_FORMAT)

        return {
            "id": self.id,
            "timestamp": timestamp,
            "user": self.user.serialize(),
            "message": self.message,
            "description": self.description,
            "classification": self.classification,
            "priority": self.priority,
            "criticity": self.criticity,
            "segment": SEGMENT,
            "manufacturer": MANUFACTURER,
            "has_comments": True if self.logs else False
        }
