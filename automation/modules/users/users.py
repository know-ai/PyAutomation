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

    def login(self, user:User, password:str, token:str)->bool:
        r"""
        Documentation here
        """            
        if self.decode_password(user=user, password=password):
            
            if token:
                
                user.token = token
            
            else:
            
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
        self._revoked_tokens = set()

    def login(self, password:str, token:str=None, username:str=None, email:str=None):
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

            # Verificar que el usuario existe antes de intentar autenticar
            if user is None:
                return None, f"User not found"
            
            # Intentar autenticar
            if self.__auth.login(user=user, password=password, token=token):
                self._revoke_other_sessions(user)
                self.active_users[user.token] = user

                return user, f"Login successful"
            else:
                # Si la autenticación falla, retornar una tupla con error
                return None, f"Invalid password"

        else:

            raise ValueError(f"You must submit username or email")
        
    def _revoke_other_sessions(self, user:User)->None:
        r"""Drop previous in-memory sessions for this user (single active session)."""
        stale = [
            session_token
            for session_token, session_user in list(self.active_users.items())
            if session_user is user or (
                getattr(session_user, "username", None) == getattr(user, "username", None)
                and session_token != getattr(user, "token", None)
            )
        ]
        if stale:
            try:
                from ...utils.user_session_audit import record_user_session_event

                record_user_session_event(
                    action="LOGOUT",
                    user=user,
                    extra="reason=session_superseded",
                )
            except Exception:
                pass
        for session_token in stale:
            self.active_users.pop(session_token, None)
            if session_token:
                self._revoked_tokens.add(session_token)
        # Bound growth of the revoked set
        if len(self._revoked_tokens) > 512:
            excess = list(self._revoked_tokens)[: len(self._revoked_tokens) - 512]
            for item in excess:
                self._revoked_tokens.discard(item)

    def is_revoked_token(self, token:str)->bool:
        return bool(token) and token in getattr(self, "_revoked_tokens", set())

    def activate_session_from_db_record(self, db_user, token:str=None)->User|None:
        r"""Rebind a DB-backed session into the in-memory active map. Never raises."""
        try:
            username = getattr(db_user, "username", None)
            if not username:
                return None
            user = self.get_by_username(username=username)
            if user is None:
                return None
            session_token = token or getattr(db_user, "token", None)
            if not session_token:
                return None
            user.token = session_token
            self.active_users[session_token] = user
            self._revoked_tokens.discard(session_token)
            return user
        except Exception:
            return None

    def rebind_sessions_from_db_tokens(self)->int:
        r"""After historian reconnect, restore active_users from persisted tokens."""
        restored = 0
        try:
            from ...dbmodels.users import Users as DbUsers
            for db_user in DbUsers.select():
                token = getattr(db_user, "token", None)
                if not token:
                    continue
                if self.activate_session_from_db_record(db_user, token=token):
                    restored += 1
        except Exception:
            return restored
        return restored

    def logout(self, token:str)->None:
        r"""
        Documentation here
        """        
        if token in self.active_users:

            user = self.active_users.pop(token)

            self.__auth.logout(user=user)
        if token:
            self._revoked_tokens.add(token)

    def signup(self, 
            username:str, 
            email:str, 
            password:str, 
            name:str=None,
            lastname:str=None,
            identifier:str=None,
            role_name:str='guest',
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
    
    def update_role(self, username:str, new_role_name:str)->tuple:
        r"""
        Updates a user's role in the CVT.

        **Parameters:**

        * **username** (str): Username of the user whose role will be updated.
        * **new_role_name** (str): New role name to assign.

        **Returns:**

        * **tuple**: (User object, status message)
        """
        user = self.get_by_username(username=username)
        if not user:
            return None, f"User {username} not found"
        
        roles = Roles()
        new_role = roles.get_by_name(name=new_role_name)
        if not new_role:
            return None, f"Role {new_role_name} not found"
        
        user.role = new_role
        
        return user, f"Role updated successfully for {username}"
    
    def _delete_all(self):
        
        self.__reset()

    def serialize(self):
        r"""
        Documentation here
        """
        return [user.serialize() for user in self.__by_username.values() if user.role.name.lower()!="sudo"]
    
users = Users()
        