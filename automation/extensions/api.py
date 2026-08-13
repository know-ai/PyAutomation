from flask import Blueprint, request
from flask_restx import abort
from flask_restx import Api as API
from ..singleton import Singleton
from functools import wraps
import logging, jwt
from ..utils.decorators import decorator
from ..dbmodels.users import Users
from ..modules.users.users import Users as CVTUsers


authorizations = {
    'apikey' : {
        'type' : 'apiKey',
        'in' : 'header',
        'name' : 'X-API-KEY'
    }
}


blueprint = Blueprint('api', __name__, url_prefix='/api')

api = API(blueprint, version='1.0', 
        title='PyAutomation API',
        description="""
        This API groups all namespaces defined in every module's resources for PyAutomation App.
        """, 
        doc='/docs',
        authorizations=authorizations
    )

users = CVTUsers()

class Api(Singleton):

    def __init__(self):

        self.app = None

    def init_app(self, app):
        r"""
        Documentation here
        """
        self.app = self.create_api(app)

        return app

    def create_api(self, app):
        r"""
        Documentation here
        """
        app.register_blueprint(blueprint)

        return api
    
    @staticmethod
    def verify_tpt(tpt:str):
        r"""
        Verify Third Party Token
        """
        from .. import server
        try:

            jwt.decode(tpt, server.config["AUTOMATION_APP_SECRET_KEY"], algorithms=["HS256"])

            return True

        except:

            return 
        
    @classmethod
    def validate_reqparser(cls, reqparser):
        def _validate_reqparser(f):
                
            @wraps(f)
            def decorated(*args, **kwargs):
                
                reqparser.parse_args() 
                result = f(*args, **kwargs)
                return result

            return decorated
        
        return _validate_reqparser
    
    @classmethod
    def token_required(cls, auth:bool=False):
        
        def _token_required(f):
            
            @wraps(f)
            def decorated(*args, **kwargs):
                if not auth:
                    return f(*args, **kwargs)

                token = None
                if 'X-API-KEY' in request.headers:
                    token = request.headers['X-API-KEY']
                elif 'Authorization' in request.headers:
                    token = request.headers['Authorization'].split('Token ')[-1]

                if not token:
                    return {'message': 'Key is missing.'}, 401

                # In-memory session first: CVT/OPC UA/real-time must keep working
                # when the remote historian is down.
                memory_user = users.get_active_user(token=token)
                if memory_user:
                    return f(*args, **kwargs)

                try:
                    db_user = Users.get_or_none(token=token)
                    if db_user:
                        return f(*args, **kwargs)
                except Exception:
                    logging.getLogger("pyautomation").debug(
                        "Token DB lookup skipped; remote database unreachable",
                        exc_info=True,
                    )

                if Api.verify_tpt(tpt=token):
                    return f(*args, **kwargs)

                return {'message': 'Invalid token'}, 401

            return decorated

        return _token_required
    
    @classmethod
    def auth_roles(cls, role_names:list[str]):
        r"""
        Decorator that restricts access to endpoints based on a list of role names.
        
        **Parameters:**
        
        * **role_names** (list[str]): List of role names allowed to access the endpoint.
        
        **Usage:**
        
        ```python
        @Api.token_required(auth=True)
        @Api.auth_roles(['admin', 'supervisor'])
        def post(self):
            # Only users with role 'admin' or 'supervisor' can access
            pass
        ```
        """
        def _auth_roles(f):
            @wraps(f)
            def decorated(*args, **kwargs):
                try:
                    token = None
                    
                    if 'X-API-KEY' in request.headers:
                        token = request.headers['X-API-KEY']
                    elif 'Authorization' in request.headers:
                        token = request.headers['Authorization'].split('Token ')[-1]
                    
                    if not token:
                        return {'message': 'Token is required'}, 401
                    
                    # Get user from token
                    current_user = users.get_active_user(token=token)
                    
                    if not current_user:
                        try:
                            db_user = Users.get_or_none(token=token)
                        except Exception:
                            db_user = None
                        if db_user:
                            # Get role from database
                            role_name = db_user.role.name.upper()
                            if role_name in [r.upper() for r in role_names]:
                                return f(*args, **kwargs)
                        return {'message': 'Invalid token or insufficient permissions'}, 401
                    
                    # Check if user's role is in the allowed list
                    user_role_name = current_user.role.name.upper()
                    allowed_roles = [r.upper() for r in role_names]
                    
                    if user_role_name in allowed_roles:
                        return f(*args, **kwargs)
                    
                    return {'message': f'Access denied. Required roles: {role_names}'}, 403
                    
                except Exception as err:
                    logger = logging.getLogger("pyautomation")
                    logger.error(str(err))
                    return {'message': 'Internal server error'}, 500
            
            return decorated
        return _auth_roles
    
    @classmethod
    def auth_role_level(cls, max_level:int):
        r"""
        Decorator that restricts access to endpoints based on role level.
        Users with role_level <= max_level are allowed access.
        
        **Parameters:**
        
        * **max_level** (int): Maximum role level allowed (inclusive). Lower numbers = higher privilege.
        
        **Usage:**
        
        ```python
        @Api.token_required(auth=True)
        @Api.auth_role_level(1)  # Only admin (level 1) and sudo (level 0) can access
        def post(self):
            # Only users with role_level <= 1 can access
            pass
        ```
        """
        def _auth_role_level(f):
            @wraps(f)
            def decorated(*args, **kwargs):
                try:
                    token = None
                    
                    if 'X-API-KEY' in request.headers:
                        token = request.headers['X-API-KEY']
                    elif 'Authorization' in request.headers:
                        token = request.headers['Authorization'].split('Token ')[-1]
                    
                    if not token:
                        return {'message': 'Token is required'}, 401
                    
                    # Get user from token
                    current_user = users.get_active_user(token=token)
                    
                    if not current_user:
                        try:
                            db_user = Users.get_or_none(token=token)
                        except Exception:
                            db_user = None
                        if db_user:
                            # Get role level from database
                            role_level = db_user.role.level
                            if role_level <= max_level:
                                return f(*args, **kwargs)
                        return {'message': 'Invalid token or insufficient permissions'}, 401
                    
                    # Check if user's role level is <= max_level
                    user_role_level = current_user.role.level
                    
                    if user_role_level <= max_level:
                        return f(*args, **kwargs)
                    
                    return {'message': f'Access denied. Required role level: <= {max_level}'}, 403
                    
                except Exception as err:
                    logger = logging.getLogger("pyautomation")
                    logger.error(str(err))
                    return {'message': 'Internal server error'}, 500
            
            return decorated
        return _auth_role_level
    
    @classmethod
    def get_current_user(cls):

        token = None

        if 'X-API-KEY' in request.headers:
                            
            token = request.headers['X-API-KEY']

        elif 'Authorization' in request.headers:
            
            token = request.headers['Authorization'].split('Token ')[-1]

        if token:

            return users.get_active_user(token=token)

        return None