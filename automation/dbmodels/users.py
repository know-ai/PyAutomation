import secrets
from peewee import CharField, IntegerField, ForeignKeyField
from ..dbmodels.core import BaseModel
from ..modules.users.users import Users as CVTUsers
from ..modules.users.roles import Roles as CVTRoles
from ..modules.users.roles import Role
from ..modules.users.users import User
from werkzeug.security import generate_password_hash, check_password_hash

users = CVTUsers()
roles = CVTRoles()

class Roles(BaseModel):
    r"""
    Database model for User Roles.
    """
    
    identifier = CharField(unique=True, max_length=16)
    name = CharField(unique=True, max_length=32)
    level = IntegerField()
    __defaults__ = [
        {"name": "sudo", "level": 0, "identifier": secrets.token_hex(4)},
        {"name": "admin", "level": 1, "identifier": secrets.token_hex(4)},
        {"name": "supervisor", "level": 2, "identifier": secrets.token_hex(4)},
        {"name": "operator", "level": 10, "identifier": secrets.token_hex(4)},
        {"name": "auditor", "level": 100, "identifier": secrets.token_hex(4)},
        {"name": "guest", "level": 256, "identifier": secrets.token_hex(4)}
    ]

    @classmethod
    def create(cls, name:str, level:int, identifier:str)->tuple:
        r"""
        Creates a new Role record.

        **Parameters:**

        * **name** (str): Role name.
        * **level** (int): Permission level (0 is highest).
        * **identifier** (str): Unique ID.

        **Returns:**

        * **tuple**: (Query object, status message)
        """
        
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
        r"""
        Retrieves a role by name.
        """
      
        return cls.get_or_none(name=name.upper())
    
    @classmethod
    def read_by_identifier(cls, identifier:str):
        r"""
        Retrieves a role by identifier.
        """
      
        return cls.get_or_none(identifier=identifier)

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Checks if a role name exists.
        """
        
        return True if cls.get_or_none(name=name.upper()) else False
    
    @classmethod
    def identifier_exist(cls, identifier:str)->bool:
        r"""
        Checks if a role identifier exists.
        """

        return True if cls.get_or_none(identifier=identifier) else False
    
    @classmethod
    def read_names(cls)->list:
        r"""
        Returns a list of all role names.
        """

        return [role.name for role in cls.select()]
    
    @classmethod
    def fill_cvt_roles(cls):
        r"""
        Loads roles from the database into the in-memory Role Manager (CVT).
        """
        for role in cls.select():

            _role = Role(
                name=role.name,
                level=role.level,
                identifier=role.identifier
            )

            roles.add(role=_role)

    def serialize(self)->dict:
        r"""
        Serializes the role record.
        """

        return {
            "id": self.id,
            "identifier": self.identifier,
            "name": self.name,
            "level": self.level
        }


class Users(BaseModel):
    r"""
    Database model for Users.
    """
    
    identifier = CharField(unique=True, max_length=16)
    username = CharField(unique=True, max_length=64)
    role = ForeignKeyField(Roles, backref='users', on_delete='CASCADE')
    email = CharField(unique=True, max_length=128)
    password = CharField()
    token = CharField(null=True)
    name = CharField(max_length=64, null=True)
    lastname = CharField(max_length=64, null=True)

    @classmethod
    def create(cls, user:User)-> dict:
        r"""
        Creates a new User record.

        **Parameters:**

        * **user** (User): An instance of the User class from the users module.

        **Returns:**

        * **tuple**: (Query object, status message)
        """

        if cls.username_exist(user.username):

            return None, f"username {user.username} is already used"

        if cls.email_exist(user.email):

            return None, f"email {user.email} is already used"
        
        if cls.identifier_exist(user.identifier):

            return None, f"identifier {user.identifier} is already used"
        
        query = cls(
            username=user.username,
            role=Roles.read_by_name(name=user.role.name),
            email=user.email,
            password=user.password,
            identifier=user.identifier,
            name=user.name,
            lastname=user.lastname,
            token=user.token
            )
        query.save()

        return query, f"User creation successful"
    
    @classmethod
    def login(cls, password:str, username:str="", email:str=""):
        r"""
        Authenticates a user and updates their session token.

        **Parameters:**

        * **password** (str): User password.
        * **username** (str, optional): Username.
        * **email** (str, optional): Email.

        **Returns:**

        * **tuple**: (User record, status message)
        """
        if username:

            user = cls.get_or_none(username=username)

        if email:

            user = cls.get_or_none(email=email)
        
        if user:

            if user.decode_password(password):
                
                if not user.token:
                    
                    user.token = cls.encode(secrets.token_hex(4))
                    user.save()
                
                users.login(password=password, token=user.token, username=username, email=email)

                return user, f"Login successfull"

            return None, f"Invalid credentials" 

        return None, f"Invalid Username or Email"      
    
    @classmethod
    def logout(cls, token:str):
        r"""
        Logs out a user by invalidating their token.

        **Parameters:**

        * **token** (str): Session token.
        """
        user = cls.get_or_none(token=token)

        if user:

            user.token = None
            user.save()

            return user, "Logout successfull"
        
        return None, "Invalid Token"

    @classmethod
    def read_by_username(cls, username:str):
        r"""
        Retrieves a user by username.
        """
   
        return cls.get_or_none(username=username)

    @classmethod
    def read_by_name(cls, name:str):
        r"""
        Retrieves a user by name (first name).
        """
   
        return cls.get_or_none(name=name)

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Checks if a user name exists.
        """

        return True if cls.get_or_none(name=name) else False
    
    @classmethod
    def username_exist(cls, username:str)->bool:
        r"""
        Checks if a username exists.
        """

        return True if cls.get_or_none(username=username) else False
    
    @classmethod
    def email_exist(cls, email:str)->bool:
        r"""
        Checks if an email exists.
        """

        return True if cls.get_or_none(email=email) else False
    
    @classmethod
    def identifier_exist(cls, identifier:str)->bool:
        r"""
        Checks if an identifier exists.
        """

        return True if cls.get_or_none(identifier=identifier) else False
    
    @classmethod
    def encode(cls, value:str)->str:
        r"""
        Hashes a value (e.g., password).
        """

        return generate_password_hash(value)
    
    def decode_password(self, password:str)->str:
        r"""
        Verifies a password against the stored hash.
        """

        return check_password_hash(self.password, password)
    
    def decode_token(self, token:str)->str:
        r"""
        Verifies a token against the stored hash.
        """

        return check_password_hash(self.token, token)
    
    @classmethod
    def update_password(cls, username:str, new_password:str)->tuple:
        r"""
        Updates a user's password.

        **Parameters:**

        * **username** (str): Username of the user whose password will be updated.
        * **new_password** (str): New plain text password to set.

        **Returns:**

        * **tuple**: (User record, status message)
        """
        user = cls.get_or_none(username=username)
        
        if not user:
            return None, f"User {username} not found"
        
        user.password = cls.encode(new_password)
        user.save()
        
        return user, f"Password updated successfully for {username}"
    
    @classmethod
    def fill_cvt_users(cls):
        r"""
        Loads users from the database into the in-memory User Manager (CVT).
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
        Serializes the user record.
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