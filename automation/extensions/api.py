from flask import Blueprint, request
from flask_restx import abort
from flask_restx import Api as API
from ..singleton import Singleton
from functools import wraps
import logging, jwt
from ..utils.decorators import decorator
from ..utils.system_user import is_system_username, system_user_path_allowed
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
    def _resolve_session_user(cls, token: str):
        r"""Resolve an authenticated user without forcing a false 'Invalid token'
        when the historian is unreachable.

        Returns ``(user, error_body, status_code)``. ``error_body`` is None on success.
        For valid TPT tokens, ``user`` may be None with no error.
        """
        if not token:
            return None, {'message': 'Key is missing.', 'code': 'AUTH_KEY_MISSING'}, 401

        memory_user = users.get_active_user(token=token)
        if memory_user:
            return memory_user, None, None

        if users.is_revoked_token(token):
            return None, {
                'message': 'Session has been superseded by another login',
                'code': 'SESSION_SUPERSEDED',
            }, 401

        db_reachable = True
        try:
            from automation import PyAutomation
            db_reachable = bool(PyAutomation().is_db_connected())
        except Exception:
            db_reachable = False

        if db_reachable:
            try:
                from ..utils.user_api_session_store import lookup_username

                session_username = lookup_username(token)
                if session_username:
                    db_user = Users.get_or_none(Users.username == session_username)
                    if db_user:
                        restored = users.activate_session_from_db_record(db_user, token=token)
                        if restored:
                            return restored, None, None
            except Exception:
                logging.getLogger("pyautomation").debug(
                    "user_api_sessions token lookup skipped",
                    exc_info=True,
                )
            try:
                db_user = Users.get_or_none(token=token)
                if db_user:
                    restored = users.activate_session_from_db_record(db_user, token=token)
                    return restored or memory_user, None, None
            except Exception:
                db_reachable = False
                logging.getLogger("pyautomation").debug(
                    "Token DB lookup skipped; remote database unreachable",
                    exc_info=True,
                )
        else:
            logging.getLogger("pyautomation").debug(
                "Token DB lookup skipped; historian marked disconnected"
            )

        if Api.verify_tpt(tpt=token):
            return None, None, None

        # Do not impersonate "logged in elsewhere" when the historian is down
        # and the in-memory session map no longer has this token.
        if not db_reachable:
            return None, {
                'message': 'Authentication backend temporarily unavailable',
                'code': 'AUTH_BACKEND_UNAVAILABLE',
            }, 503

        return None, {'message': 'Invalid token', 'code': 'SESSION_INVALID'}, 401
    
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

                _user, err, status = cls._resolve_session_user(token)
                if err is not None:
                    return err, status
                if (
                    _user is not None
                    and is_system_username(getattr(_user, "username", None))
                    and not system_user_path_allowed(request.path)
                ):
                    return {
                        "message": "System user is restricted to user management",
                        "code": "SYSTEM_USER_RESTRICTED",
                    }, 403
                return f(*args, **kwargs)

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
                    
                    current_user, err, status = cls._resolve_session_user(token)
                    if err is not None:
                        return err, status
                    if not current_user:
                        return {'message': 'Invalid token', 'code': 'SESSION_INVALID'}, 401
                    
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
                    
                    current_user, err, status = cls._resolve_session_user(token)
                    if err is not None:
                        return err, status
                    if not current_user:
                        return {'message': 'Invalid token', 'code': 'SESSION_INVALID'}, 401
                    
                    if current_user.role.level <= max_level:
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

        if not token:
            return None

        user, err, _status = cls._resolve_session_user(token)
        if err is not None:
            return None
        return user
