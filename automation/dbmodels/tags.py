from peewee import CharField
from automation.dbmodels.core import BaseModel


class Tags(BaseModel):

    id = CharField(primary_key=True, unique=True)
    name = CharField(unique=True)
    unit = CharField(max_length=250)
    data_type = CharField(max_length=250)
    description = CharField(max_length=250)
    display_name = CharField()
    opcua_address = CharField(null=True)
    node_namespace = CharField(null=True)

    @classmethod
    def create(
        cls,
        id:str,
        name:str, 
        unit:str,
        data_type:str,
        description:str,
        display_name:str,
        opcua_address:str=None,
        node_namespace:str=None
        ):
        
        if not cls.name_exists(name):
            
            tag = super().create(
                id=id,
                name=name, 
                unit=unit,
                data_type=data_type,
                description=description,
                display_name=display_name,
                opcua_address=opcua_address,
                node_namespace=node_namespace
                )
            tag.save()

            return tag
    
    @classmethod
    def name_exists(cls, name:str)->bool|None:
        r"""
        Documentation here
        """
        tag = cls.get_or_none(name=name)
        if tag:

            return True
        
    @classmethod
    def read(cls, id:str):
        
        return cls.get_or_none(id=id)
        
    @classmethod
    def read_by_name(cls, name:str):
        
        return cls.get_or_none(name=name)

    def serialize(self):
        r"""
        Documentation here
        """
        return {
            'id': self.id,
            'name': self.name,
            'unit': self.unit,
            'data_type': self.data_type,
            'description': self.description,
            'display_name': self.display_name,
            'opcua_address': self.opcua_address,
            'node_namespace': self.node_namespace
        }