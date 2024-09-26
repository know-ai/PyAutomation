from automation.singleton import Singleton
import secrets


class User:
    r"""
    Documentation here
    """
    def __init__(
            self, 
            username:str, 
            role:str, 
            email:str, 
            password:str, 
            name:str=None, 
            lastname:str=None, 
            id:str=None):

        self.id = secrets.token_hex(4)
        if id:
            self.id = id
        self.username = username
        