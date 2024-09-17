from peewee import CharField, FloatField, DateTimeField
from automation.dbmodels.core import BaseModel
from datetime import datetime
from automation import DATETIME_FORMAT


class Alarms(BaseModel):

    id = CharField(primary_key=True, unique=True, max_length=16)
    name = CharField(unique=True, max_length=64)
    tag = CharField(max_length=64)    
    trigger_type = CharField(null=True, max_length=16)
    trigger_value = FloatField()
    description = CharField(null=True, max_length=256)
    tag_alarm = CharField(null=True, max_length=64)
    state = CharField(null=True, max_length=16)
    timestamp = DateTimeField(null=True)
    acknowledged_timestamp = DateTimeField(null=True)

    @classmethod
    def create(
        cls,
        id:str,
        name:str,
        tag:str,  
        trigger_type:str,
        trigger_value:float,
        description:str=None,
        tag_alarm:str=None,
        state:str=None,
        timestamp:datetime=None,
        acknowledged_timestamp:datetime=None
        ):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        if not cls.name_exists(name):
            
            tag = super().create(
                id=id,
                name=name,
                tag=tag,  
                trigger_type=trigger_type,
                trigger_value=trigger_value,
                description=description,
                tag_alarm=tag_alarm,
                state=state,
                timestamp=timestamp,
                acknowledged_timestamp=acknowledged_timestamp
            )
            tag.save()

            return tag
    
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

            timestamp = timestamp.strftime(DATETIME_FORMAT)

        acknowledged_timestamp = self.acknowledged_timestamp
        if acknowledged_timestamp:

            acknowledged_timestamp = timestamp.strftime(DATETIME_FORMAT)

        return {
            'id': self.id,
            'name': self.name,
            'tag': self.tag,  
            'trigger_type': self.trigger_type,
            'trigger_value': self.trigger_value,
            'description': self.description,
            'tag_alarm': self.tag_alarm,
            'state': self.state,
            'timestamp': timestamp,
            'acknowledged_timestamp': acknowledged_timestamp
        }
    