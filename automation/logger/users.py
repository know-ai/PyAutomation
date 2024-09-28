# -*- coding: utf-8 -*-
"""pyhades/logger/users.py
"""
from ..modules.users.users import User
from ..dbmodels import Users, Roles
from .core import BaseEngine, BaseLogger


class UsersLogger(BaseLogger):

    def __init__(self):

        super(UsersLogger, self).__init__()

    def set_role(self, name:str, level:int, identifier:str):
        r"""
        Documentation here
        """
        return Roles.create(
            name=name,
            level=level,
            identifier=identifier
        )

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
    