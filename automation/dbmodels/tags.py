from peewee import CharField, IntegerField, FloatField
from automation.dbmodels.core import BaseModel


class Tags(BaseModel):

    id = CharField(primary_key=True, unique=True, max_length=16)
    name = CharField(unique=True, max_length=64)
    unit = CharField(max_length=64)
    display_unit = CharField(max_length=64)
    data_type = CharField(max_length=64)
    description = CharField(max_length=250)
    display_name = CharField(max_length=64)
    opcua_address = CharField(null=True, max_length=64)
    node_namespace = CharField(null=True, max_length=64)
    scan_time = IntegerField(null=True)
    dead_band = FloatField(null=True)

    @classmethod
    def create(
        cls,
        id:str,
        name:str, 
        unit:str,
        data_type:str,
        description:str,
        display_name:str=None,
        display_unit:str=None,
        opcua_address:str=None,
        node_namespace:str=None,
        scan_time:int=None,
        dead_band:float=None
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
                unit=unit,
                data_type=data_type,
                description=description,
                display_name=display_name,
                opcua_address=opcua_address,
                node_namespace=node_namespace,
                scan_time=scan_time,
                dead_band=dead_band
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
        return {
            'id': self.id,
            'name': self.name,
            'unit': self.unit,
            'data_type': self.data_type,
            'description': self.description,
            'display_name': self.display_name,
            'display_unit': self.display_unit,
            'opcua_address': self.opcua_address,
            'node_namespace': self.node_namespace,
            'scan_time': self.scan_time,
            'dead_band': self.dead_band
        }