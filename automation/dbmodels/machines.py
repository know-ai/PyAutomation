from peewee import CharField, IntegerField, ForeignKeyField, FloatField
from .core import BaseModel
from .tags import Tags


class Machines(BaseModel):

    name = CharField(unique=True)
    interval = FloatField()
    description = CharField(max_length=128)
    classification = CharField(max_length=128)
    buffer_size = IntegerField()
    buffer_roll_type = CharField(max_length=16)
    criticity = IntegerField()
    priority = IntegerField()

    @classmethod
    def create(
        cls, 
        name:str,
        interval:int,
        description:str,
        classification:str,
        buffer_size:int,
        buffer_roll_type:str,
        criticity:int,
        priority:int
        )-> dict:

        result = dict()
        data = dict()

        if not cls.name_exist(name):

            query = cls(
                name=name,
                interval=interval,
                description=description,
                classification=classification,
                buffer_size=buffer_size,
                buffer_roll_type=buffer_roll_type,
                criticity=criticity,
                priority=priority
                )
            query.save()
            
            message = f"Machine {name} created successfully"
            data.update(query.serialize())

            result.update(
                {
                    'message': message, 
                    'data': data
                }
            )
            return result

        message = f"Machine {name} is already into database"
        result.update(
            {
                'message': message, 
                'data': data
            }
        )
        return result

    @classmethod
    def read_by_name(cls, name:str)->bool:
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def read_config(cls):
        r"""
        Select all records

        You can use this method to retrieve all instances matching in the database. 

        This method is a shortcut that calls Model.select() with the given query.

        **Parameters**

        **Returns**

        * **result:** (dict) --> {'message': (str), 'data': (list) row serialized}
        """
        return {f"{query.name}": query.serialize() for query in cls.select()}

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Verify is a name exist into database

        **Parameters**

        * **name:** (str) Variable name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False
    
    def get_tags(self):

        return self.tags

    def serialize(self)-> dict:
        r"""
        Serialize database record to a jsonable object
        """

        return {
            "id": self.id,
            "name": self.name,
            "interval": self.interval,
            "description": self.description,
            "classification": self.classification,
            "buffer_size": self.buffer_size,
            "buffer_roll_type": self.buffer_roll_type,
            "criticity": self.criticity,
            "priority": self.priority
        }


class TagsMachines(BaseModel):

    tag = ForeignKeyField(Tags, backref="machines")
    machine = ForeignKeyField(Machines, backref="tags")
    default_tag_name = CharField(max_length=64, null=True)

    @classmethod
    def create(
        cls, 
        tag_name:str,
        machine_name:str,
        default_tag_name:str=None
        )-> dict:

        tag = Tags.get_or_none(name=tag_name)
        machine = Machines.get_or_none(name=machine_name)

        if not cls.get_or_none(tag=tag, machine=machine):

            query = cls(
                tag=tag,
                machine=machine,
                default_tag_name=default_tag_name
                )
            query.save()

    def serialize(self):

        return {
            "machine": self.machine.serialize(),
            "tag": self.tag.serialize(),
            "default_tag_name": self.default_tag_name
        }
