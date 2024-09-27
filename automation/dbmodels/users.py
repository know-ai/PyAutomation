from peewee import CharField, IntegerField, ForeignKeyField
from automation.dbmodels.core import BaseModel
from automation.modules.users.users import users


class Roles(BaseModel):

    identifier = CharField(unique=True, max_length=16)
    name = CharField(unique=True, max_length=32)
    level = IntegerField()

    @classmethod
    def create(cls, name:str, level:int, identifier:str)->tuple:
        
        name = name.upper()

        if cls.name_exist(name):

            return None, f"role {name} is already used"

        if cls.identifier_exist(identifier):
                
            return None, f"identifier {identifier} is already used"

        query = cls(name=name, level=level, identifier=identifier)
        query.save()
        return query, f"Role creation successful"

    @classmethod
    def read_by_name(cls, name:str):
      
        return cls.get_or_none(name=name.upper())
    
    @classmethod
    def read_by_identifier(cls, identifier:str):
      
        return cls.get_or_none(identifier=identifier)

    @classmethod
    def name_exist(cls, name:str)->bool:
        
        return True if cls.get_or_none(name=name.upper()) else False
    
    def identifier_exist(cls, identifier:str)->bool:

        return True if cls.get_or_none(identifier=identifier) else False
    
    @classmethod
    def read_names(cls)->list:

        return [role.name for role in cls.select()]

    def serialize(self)->dict:
        r"""
        Serialize database record to a jsonable object
        """

        return {
            "id": self.id,
            "identifier": self.identifier,
            "name": self.name,
            "level": self.level
        }


class Users(BaseModel):

    identifier = CharField(unique=True, max_length=16)
    username = CharField(unique=True, max_length=64)
    role = ForeignKeyField(Roles, backref='users', on_delete='CASCADE')
    email = CharField(unique=True, max_length=128)
    password = CharField(unique=True)
    name = CharField(unique=True, max_length=64, null=True)
    lastname = CharField(unique=True, max_length=64, null=True)

    @classmethod
    def create(cls, username:str, role:str, email:str, password:str, name:str=None, lastname:str=None)-> dict:

        if cls.username_exist(username):

            return None, f"username {username} is already used"

        if cls.email_exist(email):

            return None, f"email {email} is already used"
        
        user, message = users.signup(
            username=username, 
            role_name=role,
            email=email,
            password=password,
            name=name,
            lastname=lastname
            )
        
        if user:
        
            if cls.identifier_exist(user.identifier):

                return None, f"identifier {user.identifier} is already used"

            query = cls(
                username=username,
                role=user.role.name,
                email=email,
                password=user.password,
                identifier=user.identifier,
                name=name,
                lastname=lastname
                )
            query.save()

            return query, f"User creation successful"
        
        return None, message

    @classmethod
    def read_by_name(cls, name:str):
   
        return cls.get_or_none(name=name)

    @classmethod
    def name_exist(cls, name:str)->bool:

        return True if cls.get_or_none(name=name) else False
    
    @classmethod
    def username_exist(cls, username:str)->bool:

        return True if cls.get_or_none(username=username) else False
    
    @classmethod
    def email_exist(cls, email:str)->bool:

        return True if cls.get_or_none(email=email) else False
    
    @classmethod
    def identifier_exist(cls, identifier:str)->bool:

        return True if cls.get_or_none(identifier=identifier) else False
    
    @classmethod
    def fill_cvt_users(cls):
        r"""
        Documentation here
        """
        for user in cls.select():

            users.signup(
                username=user.username,
                role_name=user.role.name,
                email=user.email,
                password=user.password,
                name=user.name,
                lastname=user.lastname,
                identifier=user.identifier,
                encode_password=False
            )

    def serialize(self)-> dict:
        r"""
        Serialize database record to a jsonable object
        """

        return {
            "id": self.id,
            "identifier": self.identifier,
            "username": self.username,
            "email": self.email,
            "role": self.role.serialize(),
            "name": self.name,
            "lastname": self.lastname
        }