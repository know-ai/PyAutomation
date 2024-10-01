import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from ...singleton import Singleton
from .roles import Role, Roles



class User:
    r"""
    Documentation here
    """
    def __init__(
            self, 
            username:str, 
            role:Role, 
            email:str, 
            password:str, 
            name:str=None, 
            lastname:str=None, 
            identifier:str=None):

        self.identifier = secrets.token_hex(4)
        if identifier:
            self.identifier = identifier
        self.username = username
        self.role = role
        self.email = email
        self.password = password
        self.name = name
        self.lastname = lastname 
        self.token = None

    def logout(self):
        r"""
        Documentation here
        """
        self.token = None

    def serialize(self):
        r"""
        Documentation here
        """
        return {
            "identifier": self.identifier,
            "username": self.username,
            "role": self.role.serialize(),
            "email": self.email,
            "name": self.name,
            "lastname": self.lastname
        }


class Auth:
    r"""
    Documentation here
    """

    def login(self, user:User, password:str)->bool:
        r"""
        Documentation here
        """            
        if self.decode_password(user=user, password=password):
            
            user.token = self.encode(secrets.token_hex(4))
            
            return True
        
        return False
    
    def verify_credentials(self, user:User, password:str)->bool:
        r"""
        Documentation here
        """            
        if self.decode_password(user=user, password=password):

            return True
        
        return False
    
    def logout(self, user:User)->None:
        r"""
        Documentation here
        """
        user.logout()
    
    def encode(self, value:str)->str:

        return generate_password_hash(value)

    def decode_password(self, user:User, password:str)->str:

        return check_password_hash(user.password, password)
    
    def decode_token(self, user:User, token:str)->str:

        return check_password_hash(user.token, token)
    
    def signup(
            self,
            username:str, 
            role:Role, 
            email:str, 
            password:str, 
            name:str=None, 
            lastname:str=None,
            identifier:str=None,
            encode_password:bool=True
        )->User:
        r"""
        Documentation here
        """

        return User(
            username=username,
            role=role,
            email=email,
            password=self.encode(value=password) if encode_password else password,
            name=name,
            lastname=lastname,
            identifier=identifier if identifier else secrets.token_hex(4)
        )

    
class Users(Singleton):
    r"""
    Documentation here
    """

    def __init__(self):

        self.__auth = Auth()
        self.__reset()

    def __reset(self):

        self.active_users = dict()                      # Save by token
        self.__by_identifier = dict()
        self.__by_username = dict()
        self.__by_email = dict()

    def login(self, password:str, username:str=None, email:str=None):
        r"""
        Documentation here
        """
        if username or email:

            if username:
            
                if not self.check_username(username=username):

                    return None, f"{username} is not valid"
                
                user = self.get_by_username(username=username)

            elif email:

                if not self.check_email(email=email):

                    return None, f"{email} is not valid"
                
                user = self.get_by_email(email=email)

            if self.__auth.login(user=user, password=password):
                
                self.active_users[user.token] = user

                return user, f"Login successful"

        else:

            raise ValueError(f"You must submit username or email")
        
    def logout(self, token:str)->None:
        r"""
        Documentation here
        """        
        if token in self.active_users:

            user = self.active_users.pop(token)

            self.__auth.logout(user=user)

    def signup(self, 
            username:str, 
            role_name:str, 
            email:str, 
            password:str, 
            name:str=None, 
            lastname:str=None,
            identifier:str=None,
            encode_password:bool=True
            )->tuple:
        r"""
        Documentation here
        """
        message = f"{username} created successfully"
        if not self.check_username(username=username):

            if not self.check_email(email=email):
                
                roles = Roles()
                role = roles.get_by_name(name=role_name)

                if role:
                    
                    user = self.__auth.signup(
                        username=username,
                        role=role,
                        email=email,
                        password=password,
                        name=name,
                        lastname=lastname,
                        identifier=identifier,
                        encode_password=encode_password
                    )
                    
                    self.__by_identifier[user.identifier] = user
                    self.__by_username[user.username] = user
                    self.__by_email[user.email] = user
                    return user, message
                
                else:

                    return None, f"role: {role_name} not exists"
            
            else:

                return None, f"Email: {email} already exists"
            
        else:

            return None, f"username: {username} already exists"

    def verify_credentials(self, password:str, username:str=None, email:str=None)->bool:
        r"""
        Documentation here
        """
        if username or email:

            if username:
            
                if not self.check_username(username=username):

                    return False, f"{username} is not valid"
                
                user = self.get_by_username(username=username)

            elif email:

                if not self.check_email(email=email):

                    return False, f"{email} is not valid"
                
                user = self.get_by_email(email=email)

            return self.__auth.verify_credentials(user=user, password=password), f"Credentials valid"

        else:

            return False, "You must submit username or email"

    def get(self, identifier:str)->User:
        r"""
        Documentation here
        """
        if identifier in self.__by_identifier:
            
            return self.__by_identifier[identifier]

    def get_active_user(self, token:str)->User:
        r"""
        Documentation here
        """
        if token in self.active_users:

            return self.active_users[token]

    def get_by_username(self, username:str)->User:
        r"""
        Documentation here
        """
        if username in self.__by_username:

            return self.__by_username[username]
        
    def get_by_email(self, email:str)->User:
        r"""
        Documentation here
        """
        if email in self.__by_email:

            return self.__by_email[email]

    def check_username(self, username:str)->bool:
        r"""
        Documentation here
        """
        if self.get_by_username(username=username):

            return True
        
        return False

    def check_email(self, email:str)->bool:
        r"""
        Documentation here
        """
        if self.get_by_email(email=email):

            return True
        
        return False
    
    def encode(self, value:str)->str:

        return generate_password_hash(value)
    
    def _delete_all(self):
        
        self.__reset()

    def serialize(self):
        r"""
        Documentation here
        """
        return [user.serialize() for user in self.__by_username.values()]
    
users = Users()
        