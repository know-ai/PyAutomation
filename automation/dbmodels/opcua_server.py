from peewee import CharField, ForeignKeyField
from ..dbmodels.core import BaseModel

class AccessType(BaseModel):
    
    name = CharField(unique=True)

    @classmethod
    def create(cls, name:str="Read")-> dict:
        r"""Documentation here
        """
        if name.lower()=="read" or name.lower()=="write" or name.lower()=="readwrite":

            access_type_obj = cls.select().where(cls.name == name).exists()
            
            if not access_type_obj:
                query = cls(name=name)
                query.save()  
                return query
            
        return cls.read_by_name(name=name)

    @classmethod
    def read_by_name(cls, name:str)->bool:
        r"""
 
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""

        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serialize database record to a jsonable object
        """

        return {
            "id": self.id,
            "name": self.name
        }


class OPCUAServer(BaseModel):
    
    name = CharField(unique=True)
    namespace = CharField(unique=True)
    access_type = ForeignKeyField(AccessType, null=True)

    @classmethod
    def create(cls, name:str, namespace:str, access_type:str)-> dict:
        r"""Documentation here
        """
        if not cls.name_exist(name=name):
            
            if not cls.namespace_exist(namespace=namespace):
                
                if AccessType.name_exist(name=access_type):
                    access_type_obj = AccessType.read_by_name(name=access_type)
                else:
                    access_type_obj = AccessType.create(name=namespace)

                if access_type_obj:

                    query = cls(
                        name=name,
                        namespace=namespace,
                        access_type=access_type_obj
                        )
                    query.save()

                    return query

    @classmethod
    def read_by_name(cls, name:str)->bool:
        r"""
 
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None
    
    @classmethod
    def read_by_namespace(cls, namespace:str)->bool:
        r"""
 
        """
        query = cls.get_or_none(namespace=namespace)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""

        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False
    
    @classmethod
    def namespace_exist(cls, namespace:str)->bool:
        r"""

        """
        query = cls.get_or_none(namespace=namespace)
        
        if query is not None:

            return True
        
        return False
    
    @classmethod
    def update_access_type(cls, namespace:str, access_type:str)-> dict:
        r""""
        Update a single record

        Once a model instance has a primary key, you UPDATE a field by its id. 
        The model's primary key will not change:
        """
        obj = cls.get_or_none(namespace=namespace)
        
        if obj:
            
            if AccessType.name_exist(name=access_type):
                access_type_obj = AccessType.read_by_name(name=access_type)
            else:
                access_type_obj = AccessType.create(name=access_type)

            if access_type_obj:
                
                query = cls.update(access_type=access_type_obj).where(cls.id == obj.id)
                query.execute()
                return query

    def serialize(self)-> dict:
        r"""
        Serialize database record to a jsonable object
        """

        return {
            "id": self.id,
            "name": self.name,
            "access_type": self.access_type.serialize()
        }