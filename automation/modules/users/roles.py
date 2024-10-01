import secrets
from ...singleton import Singleton


class Role:
    r"""
    Documentation here
    """

    def __init__(self, name:str, level:int, identifier:str=None):
        
        _identifier = secrets.token_hex(4)
        
        if identifier:

            _identifier = identifier

        self.identifier = _identifier
        self.name:str = name
        self.level:int = level

    def serialize(self):
        r"""
        Documentation here
        """
        return {
            "identifier": self.identifier,
            "name": self.name,
            "level": self.level
        }
    

class Roles(Singleton):
    r"""
    Documentation here
    """

    def __init__(self):

        self.roles = dict()

    def add(self, role:Role)->str:
        r"""
        Documentation here
        """
        if isinstance(role, Role):

            if not self.check_role_name(name=role.name):

                self.roles[role.identifier] = role

                return role.identifier, f"role creation successful"
            
            return None, f"role {role.name} is already used"

        else:

            raise TypeError(f"{role} must be a Role instale")
        
    def get(self, id:str)->Role:
        r"""
        Documentation here
        """
        if id in self.roles:

            return self.roles[id]
        
    def get_by_name(self, name:str)->Role:
        r"""
        Documentation here
        """
        for _, role in self.roles.items():

            if name.lower()==role.name.lower():

                return role
            
    def get_names(self)->list:
        r"""
        Documentation here
        """
        return [role.name for _, role in self.roles.items()]
    
    def put(self, id:str, **kwargs):
        r"""
        Documentation here
        """
        if id in self.roles:
            role = self.roles[id]
            fields = {key: value for key, value in kwargs.items() if key in role.serialize()}
            self.roles[id].__dict__.update(fields)

    def delete(self, id:str)->dict:
        r"""
        Documentation here
        """
        if id in self.roles:
            
            return self.roles.pop(id)
        
    def _delete_all(self):

        self.roles = dict()
    
    def check_role_name(self, name:str):
        r"""
        Documentation here
        """
        if self.get_by_name(name=name):

            return True
        
        return False
    
    def serialize(self):
        r"""
        Documentation here
        """
        return [role.serialize() for _, role in self.roles.items()]
    
roles = Roles()