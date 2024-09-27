from automation.singleton import Singleton
from .roles import Role, Roles
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

# roles = Roles()

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
            id:str=None):

        self.id = secrets.token_hex(4)
        if id:
            self.id = id
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


class Auth:
    r"""
    Documentation here
    """

    def login(self, user:User, password:str)->bool:
        r"""
        Documentation here
        """            
        if self.decode_password(user=user, password=password):
            
            user.token = self.code(secrets.token_hex(4))
            
            return True
        
        return False
    
    def logout(self, user:User)->None:
        r"""
        Documentation here
        """
        user.logout()
    
    def code(self, value:str)->str:

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
            lastname:str=None
        )->User:
        r"""
        Documentation here
        """

        return User(
            username=username,
            role=role,
            email=email,
            password=self.code(value=password),
            name=name,
            lastname=lastname,
            id=secrets.token_hex(4)
        )

    
class Users(Singleton):
    r"""
    Documentation here
    """

    def __init__(self):

        self.__auth = Auth()
        self.active_users = dict()                      # Save by token
        self.__by_id = dict()
        self.__by_username = dict()
        self.__by_email = dict()
        self.roles = Roles()

    def login(self, password:str, username:str=None, email:str=None):
        r"""
        Documentation here
        """
        if username or email:

            if username:
            
                if not self.check_username(username=username):

                    raise NameError(f"{username} is not valid")
                
                user = self.get_by_username(username=username)

            elif email:

                if not self.check_email(email=email):

                    raise NameError(f"{email} is not valid")
                
                user = self.get_by_email(email=email)

            if self.__auth.login(user=user, password=password):
                
                self.active_users[user.token] = user

                return True

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
            lastname:str=None):
        r"""
        Documentation here
        """
        if not self.check_username(username=username):

            if not self.check_email(email=email):

                role = self.roles.get_by_name(name=role_name)

                if role:

                    user = self.__auth.signup(
                        username=username,
                        role=role,
                        email=email,
                        password=password,
                        name=name,
                        lastname=lastname
                    )

                    self.__by_id[user.id] = user
                    self.__by_username[user.username] = user
                    self.__by_email[user.email] = user
                    return user

    def get(self, id:str)->User:
        r"""
        Documentation here
        """
        if id in self.__by_id:
            
            return self.__by_id[id]

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
    
    def code(self, value:str)->str:

        return generate_password_hash(value)
        