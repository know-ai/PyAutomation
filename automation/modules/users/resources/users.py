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
ns = Namespace('Users', description='User Management and Authentication')
app = PyAutomation()
users = CVTUsers()

@ns.route('/')
class UsersCollection(Resource):

    @api.doc(security='apikey', description="Retrieves a list of all registered users.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    def get(self):
        """
        Get all users.

        Retrieves a list of all users currently registered in the system.
        """

        return users.serialize(), 200

@ns.route('/signup')
class SignUpResource(Resource):
    
    @Api.validate_reqparser(reqparser=signup_parser)
    @api.doc(security='apikey', description="Registers a new user.")
    @api.response(200, "User created successfully")
    @api.response(400, "User creation failed")
    @ns.expect(signup_parser)
    def post(self):
        """
        User signup.

        Registers a new user with the provided credentials and role.
        """
        args = signup_parser.parse_args()
        user, message = app.signup(**args)
        
        if user:

            return user.serialize(), 200
        
        return message, 400


@ns.route('/login')
class LoginResource(Resource):

    @Api.validate_reqparser(reqparser=login_parser)
    @api.doc(security='apikey', description="Authenticates a user and returns an API token.")
    @api.response(200, "Login successful")
    @api.response(403, "Invalid credentials")
    @ns.expect(login_parser)
    def post(self):
        """
        User login.

        Authenticates a user using username/email and password. Returns an API key/token.
        """
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
    
    @api.doc(security='apikey', description="Verifies if the provided credentials are valid without logging in.")
    @api.response(200, "Success (True/False)")
    @Api.token_required(auth=True)
    @Api.validate_reqparser(reqparser=login_parser)
    @ns.expect(login_parser)
    def post(self):
        """
        Verify credentials.

        Checks if the provided username/password combination is valid.
        """
        args = login_parser.parse_args()
        credentials_valid, _ = users.verify_credentials(**args)
        return credentials_valid, 200
    
@ns.route('/<username>')
@api.param('username', 'The username')
class UserResource(Resource):
    
    @api.doc(security='apikey', description="Retrieves information about a specific user.")
    @api.response(200, "Success")
    @api.response(400, "User not found")
    @Api.token_required(auth=True)
    def get(self, username):
        """
        Get user info.

        Retrieves detailed information about a specific user by username.
        """
        
        user = users.get_by_username(username=username)

        if user:

            return user.serialize(), 200

        return f"{username} is not a valid username", 400


@ns.route('/logout')
class LogoutResource(Resource):

    @api.doc(security='apikey', description="Logs out the current user and invalidates the token.")
    @api.response(200, "Logout successful")
    @Api.token_required(auth=True)
    def post(self):
        """
        User logout.

        Invalidates the current session token.
        """
        if 'X-API-KEY' in request.headers:
                            
            token = request.headers['X-API-KEY']

        elif 'Authorization' in request.headers:
            
            token = request.headers['Authorization'].split('Token ')[-1]
        
        _, message = Users.logout(token=token)

        return message, 200