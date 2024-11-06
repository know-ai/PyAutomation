from flask import request
from datetime import datetime
from flask_restx import Namespace, Resource
from .models.users import signup_parser, login_parser
from .... import PyAutomation, TIMEZONE, _TIMEZONE
from ....extensions.api import api
from ....extensions import _api as Api
from ....modules.users.users import Users as CVTUsers
from ....dbmodels.users import Users

DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S"
ns = Namespace('Users', description='Users')
app = PyAutomation()
users = CVTUsers()

@ns.route('/')
class UsersResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self):
        """Get all usernames"""

        return users.serialize(), 200

@ns.route('/signup')
class SignUpResource(Resource):
    
    @Api.validate_reqparser(reqparser=signup_parser)
    @ns.expect(signup_parser)
    def post(self):
        """User signup"""
        args = signup_parser.parse_args()
        user, message = app.signup(**args)
        
        if user:

            return user.serialize(), 200
        
        return message, 400


@ns.route('/login')
class LoginResource(Resource):

    @Api.validate_reqparser(reqparser=login_parser)
    @ns.expect(login_parser)
    def post(self):
        """User login"""
        args = login_parser.parse_args()
        user, message = app.login(**args)

        if user:

            return {
                "apiKey": user.token,
                "role": user.role.name,
                "role_level": user.role.level,
                "datetime": datetime.now(TIMEZONE).strftime(DATETIME_FORMAT),
                "timezone": _TIMEZONE
                }, 200

        return message, 403
    

@ns.route('/credentials_are_valid')
class VerifyCredentialsResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(login_parser)
    def post(self):
        """Verify user credentials"""
        credentials_valid, _ = users.verify_credentials(**api.payload)
        return credentials_valid, 200
    
@ns.route('/<username>')
class UserResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self, username):
        """Get user information"""
        
        user = users.get_by_username(username=username)

        if user:

            return user.serialize(), 200

        return f"{username} is not a valid username", 400


@ns.route('/logout')
class LogoutResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def post(self):
        """User logout"""
        if 'X-API-KEY' in request.headers:
                            
            token = request.headers['X-API-KEY']

        elif 'Authorization' in request.headers:
            
            token = request.headers['Authorization'].split('Token ')[-1]
        
        _, message = Users.logout(token=token)

        return message, 200