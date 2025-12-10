from peewee import CharField, IntegerField, ForeignKeyField, FloatField
from .core import BaseModel
from .tags import Tags


class Machines(BaseModel):
    r"""
    Database model for State Machines configuration.
    """
    
    identifier = CharField(unique=True)
    name = CharField(unique=True)
    interval = FloatField()
    threshold = FloatField(null=True)
    on_delay = IntegerField(null=True)
    description = CharField(max_length=128)
    classification = CharField(max_length=128)
    buffer_size = IntegerField()
    buffer_roll_type = CharField(max_length=16)
    criticity = IntegerField()
    priority = IntegerField()

    @classmethod
    def create(
        cls, 
        identifier:str,
        name:str,
        interval:int,
        description:str,
        classification:str,
        buffer_size:int,
        buffer_roll_type:str,
        criticity:int,
        priority:int,
        threshold:float=None,
        on_delay:int=None
        )-> dict:
        r"""
        Creates a new Machine record.

        **Parameters:**

        * **identifier** (str): Unique identifier.
        * **name** (str): Machine name.
        * **interval** (int): Execution interval.
        * **description** (str): Description.
        * **classification** (str): Machine type.
        * **buffer_size** (int): Data buffer size.
        * **buffer_roll_type** (str): Buffer roll strategy.
        * **criticity** (int): Criticity level.
        * **priority** (int): Priority level.

        **Returns:**

        * **dict**: Result status and data.
        """

        result = dict()
        data = dict()

        if not cls.name_exist(name):

            query = cls(
                identifier=identifier,
                name=name,
                interval=interval,
                description=description,
                classification=classification,
                buffer_size=buffer_size,
                buffer_roll_type=buffer_roll_type,
                criticity=criticity,
                priority=priority,
                threshold=threshold,
                on_delay=on_delay
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
        r"""
        Retrieves a machine by name.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def read_config(cls):
        r"""
        Retrieves configuration for all machines.

        **Returns:**

        * **dict**: Map of Machine Name -> Configuration.
        """
        return {f"{query.name}": query.serialize() for query in cls.select()}

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Checks if a machine name exists.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False
    
    def get_tags(self):
        r"""
        Returns related tags.
        """
        return self.tags

    def serialize(self)-> dict:
        r"""
        Serializes the machine record.
        """

        return {
            "id": self.id,
            "identifier": self.identifier,
            "name": self.name,
            "interval": self.interval,
            "description": self.description,
            "classification": self.classification,
            "buffer_size": self.buffer_size,
            "buffer_roll_type": self.buffer_roll_type,
            "criticity": self.criticity,
            "priority": self.priority,
            "threshold": self.threshold,
            "on_delay": self.on_delay
        }


class TagsMachines(BaseModel):
    r"""
    Many-to-Many relationship between Tags and Machines.
    """
    
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
        r"""
        Links a Tag to a Machine.

        **Parameters:**

        * **tag_name** (str): Name of the tag.
        * **machine_name** (str): Name of the machine.
        * **default_tag_name** (str, optional): Alias for the tag within the machine context.
        """

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
        r"""
        Serializes the relationship.
        """
        return {
            "machine": self.machine.serialize(),
            "tag": self.tag.serialize(),
            "default_tag_name": self.default_tag_name
        }