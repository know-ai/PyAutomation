# -*- coding: utf-8 -*-
"""automation/logger/users.py

This module implements the Users Logger, responsible for persisting user accounts,
role definitions, and logging user authentication events.
"""
from ..modules.users.users import User
from ..dbmodels import Users, Roles
from .core import BaseEngine, BaseLogger
from ..utils.decorators import db_rollback


class UsersLogger(BaseLogger):
    r"""
    Logger class specialized for User Management persistence.
    """

    def __init__(self):

        super(UsersLogger, self).__init__()

    @db_rollback
    def set_role(self, name:str, level:int, identifier:str):
        r"""
        Creates a new user role in the database.

        **Parameters:**

        * **name** (str): Role name (e.g., "admin").
        * **level** (int): Permission level (e.g., 100).
        * **identifier** (str): Unique role ID.
        """
        return Roles.create(
            name=name,
            level=level,
            identifier=identifier
        )

    @db_rollback
    def set_user(
            self, 
            user:User
        ):
        r"""
        Creates a new user in the database.

        **Parameters:**

        * **user** (User): User object containing name, password, email, roles.
        """
        return Users.create(
            user=user
        )
    
    @db_rollback
    def login(
            self, 
            password:str,
            username:str="",
            email:str=""
        ):
        r"""
        Authenticates a user against the database.

        **Parameters:**

        * **password** (str): Plain text password.
        * **username** (str, optional): Username.
        * **email** (str, optional): Email.

        **Returns:**

        * **tuple**: (User object, Message string).
        """
        return Users.login(
            password=password,
            username=username,
            email=email
        )
    
    @db_rollback
    def update_password(self, username:str, new_password:str):
        r"""
        Updates a user's password in the database.

        **Parameters:**

        * **username** (str): Username of the user.
        * **new_password** (str): New plain text password.
        """
        return Users.update_password(
            username=username,
            new_password=new_password
        )
    
class UsersLoggerEngine(BaseEngine):
    r"""
    Thread-safe Engine for the UsersLogger.
    """

    def __init__(self):

        super(UsersLoggerEngine, self).__init__()
        self.logger = UsersLogger()

    def set_role(self, name:str, level:int, identifier:str):
        r"""
        Thread-safe role creation.
        """
        _query = dict()
        _query["action"] = "set_role"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["level"] = level
        _query["parameters"]["identifier"] = identifier
        
        return self.query(_query)
    
    def set_user(self, user:User):
        r"""
        Thread-safe user creation.
        """
        _query = dict()
        _query["action"] = "set_user"
        _query["parameters"] = dict()
        _query["parameters"]["user"] = user
        
        return self.query(_query)
    
    def login(self,password:str, username:str="", email:str=""):
        r"""
        Thread-safe login.
        """
        _query = dict()
        _query["action"] = "login"
        _query["parameters"] = dict()
        _query["parameters"]["password"] = password
        _query["parameters"]["username"] = username
        _query["parameters"]["email"] = email
        
        return self.query(_query)
    
    def update_password(self, username:str, new_password:str):
        r"""
        Thread-safe password update.
        """
        _query = dict()
        _query["action"] = "update_password"
        _query["parameters"] = dict()
        _query["parameters"]["username"] = username
        _query["parameters"]["new_password"] = new_password
        
        return self.query(_query)
