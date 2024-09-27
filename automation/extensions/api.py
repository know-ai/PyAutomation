from flask import Blueprint, request
from flask_restx import Api as API
from automation.singleton import Singleton
from functools import wraps
import logging, jwt
from automation import Users
from werkzeug.security import check_password_hash


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
        from automation import server
        try:

            jwt.decode(tpt, server.config["TPT_TOKEN"], algorithms=["HS256"])

            return True

        except:

            return False
    
    @classmethod
    def token_required(cls, auth:bool=False):
        
        def _token_required(f):
            
            @wraps(f)
            def decorated(*args, **kwargs):
                try:

                    if auth:

                        token = None

                        if 'X-API-KEY' in request.headers:
                            
                            token = request.headers['X-API-KEY']

                        elif 'Authorization' in request.headers:
                            
                            token = request.headers['Authorization'].split('Token ')[-1]

                        if not token:
                            
                            return {'message' : 'Key is missing.'}, 401
                        
                        users = Users()
                        user = users.get_active_user(token=token)

                        if user:

                            return f(*args, **kwargs)

                        if Api.verify_tpt(tpt=token):
                    
                            return f(*args, **kwargs)

                        return {'message' : 'Invalid token'}, 401                  
                
                except Exception as err:

                    logging.ERROR(str(err))

            return decorated

        return _token_required