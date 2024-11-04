# -*- coding: utf-8 -*-
"""pyhades/logger/users.py
"""
from ..modules.users.users import User
from ..dbmodels import Users, Roles
from .core import BaseEngine, BaseLogger
from ..utils.decorators import db_rollback


class UsersLogger(BaseLogger):

    def __init__(self):

        super(UsersLogger, self).__init__()

    @db_rollback
    def set_role(self, name:str, level:int, identifier:str):
        r"""
        Documentation here
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
        Documentation here
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
        Documentation here
        """
        return Users.login(
            password=password,
            username=username,
            email=email
        )
    
class UsersLoggerEngine(BaseEngine):
    r"""
    Users logger Engine class for Tag thread-safe database logging.

    """

    def __init__(self):

        super(UsersLoggerEngine, self).__init__()
        self.logger = UsersLogger()

    def set_role(self, name:str, level:int, identifier:str):

        _query = dict()
        _query["action"] = "set_role"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["level"] = level
        _query["parameters"]["identifier"] = identifier
        
        return self.query(_query)
    
    def set_user(self, user:User):

        _query = dict()
        _query["action"] = "set_user"
        _query["parameters"] = dict()
        _query["parameters"]["user"] = user
        
        return self.query(_query)
    
    def login(self,password:str, username:str="", email:str=""):

        _query = dict()
        _query["action"] = "login"
        _query["parameters"] = dict()
        _query["parameters"]["password"] = password
        _query["parameters"]["username"] = username
        _query["parameters"]["email"] = email
        
        return self.query(_query)
    