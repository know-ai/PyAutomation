from flask import request
from datetime import datetime, timezone
import jwt
import logging
from flask_restx import Namespace, Resource
from .models.users import signup_parser, login_parser, change_password_parser, reset_password_parser, create_tpt_parser
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
    @api.doc(security=None, description="Registers a new user.")
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
    @api.doc(security=None, description="Authenticates a user and returns an API token.")
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

@ns.route('/change_password')
class ChangePasswordResource(Resource):

    @Api.validate_reqparser(reqparser=change_password_parser)
    @api.doc(security='apikey', description="Changes a user's password with role-based authorization.")
    @api.response(200, "Password changed successfully")
    @api.response(400, "Invalid request or authorization denied")
    @api.response(401, "Unauthorized")
    @ns.expect(change_password_parser)
    @Api.token_required(auth=True)
    def post(self):
        """
        Change password.

        Changes a user's password following role-based authorization rules:
        - Sudo users can only change passwords of admin users (not their own)
        - Admin users can change passwords of users with role_level >= admin
        - Other roles can only change their own password
        - When changing own password, current password must be provided and validated
        """
        # Get token from headers
        token = None
        if 'X-API-KEY' in request.headers:
            token = request.headers['X-API-KEY']
        elif 'Authorization' in request.headers:
            token = request.headers['Authorization'].split('Token ')[-1]
        
        if not token:
            return {'message': 'Token is required'}, 401

        # Get current user from token
        current_user = users.get_active_user(token=token)
        if not current_user:
            return {'message': 'Invalid token or user not found'}, 401

        # Parse arguments
        args = change_password_parser.parse_args()
        target_username = args['target_username']
        new_password = args['new_password']
        current_password = args.get('current_password')

        # Get target user
        target_user = users.get_by_username(username=target_username)
        if not target_user:
            return {'message': f'User {target_username} not found'}, 400

        # Extract role information
        current_role_name = current_user.role.name.upper()
        current_role_level = current_user.role.level
        target_role_name = target_user.role.name.upper()
        target_role_level = target_user.role.level

        # Check if changing own password
        is_own_password = current_user.username == target_username

        # Business logic validation - API level restrictions
        if current_role_name == "SUDO":
            # Sudo can only change admin passwords, not own password
            if is_own_password:
                return {'message': 'Sudo users cannot change their own password'}, 400
            if target_role_name != "ADMIN":
                return {'message': 'Sudo users can only change passwords of admin users'}, 400
        elif current_role_name == "ADMIN":
            # Admin can change passwords of users with role_level >= admin
            if target_role_level < current_role_level:
                return {'message': f'Admin users cannot change passwords of users with role level lower than {current_role_level}'}, 400
        else:
            # Other roles can only change their own password
            if not is_own_password:
                return {'message': 'You can only change your own password'}, 400

        # If changing own password, validate current password is provided
        if is_own_password:
            if not current_password:
                return {'message': 'Current password is required when changing your own password'}, 400

        # Call core method (internal, no restrictions)
        result, status_msg = app.change_password(
            target_username=target_username,
            new_password=new_password,
            current_password=current_password
        )

        if result:
            return {'message': status_msg}, 200
        else:
            return {'message': status_msg}, 400

@ns.route('/reset_password')
class ResetPasswordResource(Resource):

    @Api.validate_reqparser(reqparser=reset_password_parser)
    @api.doc(security='apikey', description="Resets a user's password (for forgotten password) with role-based authorization.")
    @api.response(200, "Password reset successfully")
    @api.response(400, "Invalid request or authorization denied")
    @api.response(401, "Unauthorized")
    @ns.expect(reset_password_parser)
    @Api.token_required(auth=True)
    def post(self):
        """
        Reset password.

        Resets a user's password when forgotten, following role-based authorization rules:
        - Sudo users can only reset passwords of admin users (not their own)
        - Admin users can reset passwords of users with role_level >= admin
        - Other roles can only reset their own password
        - No current password validation is required (forgotten password scenario)
        """
        # Get token from headers
        token = None
        if 'X-API-KEY' in request.headers:
            token = request.headers['X-API-KEY']
        elif 'Authorization' in request.headers:
            token = request.headers['Authorization'].split('Token ')[-1]
        
        if not token:
            return {'message': 'Token is required'}, 401

        # Get current user from token
        current_user = users.get_active_user(token=token)
        if not current_user:
            return {'message': 'Invalid token or user not found'}, 401

        # Parse arguments
        args = reset_password_parser.parse_args()
        target_username = args['target_username']
        new_password = args['new_password']

        # Get target user
        target_user = users.get_by_username(username=target_username)
        if not target_user:
            return {'message': f'User {target_username} not found'}, 400

        # Extract role information
        current_role_name = current_user.role.name.upper()
        current_role_level = current_user.role.level
        target_role_name = target_user.role.name.upper()
        target_role_level = target_user.role.level

        # Check if resetting own password
        is_own_password = current_user.username == target_username

        # Business logic validation - API level restrictions
        if current_role_name == "SUDO":
            # Sudo can only reset admin passwords, not own password
            if is_own_password:
                return {'message': 'Sudo users cannot reset their own password'}, 400
            if target_role_name != "ADMIN":
                return {'message': 'Sudo users can only reset passwords of admin users'}, 400
        elif current_role_name == "ADMIN":
            # Admin can reset passwords of users with role_level >= admin
            if target_role_level < current_role_level:
                return {'message': f'Admin users cannot reset passwords of users with role level lower than {current_role_level}'}, 400
        else:
            # Other roles can only reset their own password
            if not is_own_password:
                return {'message': 'You can only reset your own password'}, 400

        # Call core method (internal, no restrictions, no current password validation)
        result, status_msg = app.reset_password(
            target_username=target_username,
            new_password=new_password
        )

        if result:
            return {'message': status_msg}, 200
        else:
            return {'message': status_msg}, 400

@ns.route('/create_tpt')
class CreateTPTResource(Resource):

    @Api.validate_reqparser(reqparser=create_tpt_parser)
    @api.doc(security='apikey', description="Creates a Third Party Token (TPT) JWT for a specific role. Only sudo users can access this endpoint.")
    @api.response(200, "Token created successfully")
    @api.response(400, "Invalid request")
    @api.response(401, "Unauthorized")
    @api.response(403, "Forbidden - Sudo access required")
    @ns.expect(create_tpt_parser)
    @Api.token_required(auth=True)
    @Api.auth_roles(['sudo'])
    def post(self):
        """
        Create Third Party Token (TPT).

        Creates a JWT token for third-party integration with a specific role embedded.
        This endpoint is restricted to sudo users only.
        
        The token is signed using AUTOMATION_APP_SECRET_KEY and can be used
        for third-party API authentication.
        """
        # Parse arguments
        args = create_tpt_parser.parse_args()
        role_name = args['role_name']

        try:
            # Create JWT payload
            payload = {
                "created_on": datetime.now(timezone.utc).strftime(app.cvt.DATETIME_FORMAT),
                "role": role_name
            }
            
            # Encode token using AUTOMATION_APP_SECRET_KEY
            token = jwt.encode(
                payload, 
                app.server.config['AUTOMATION_APP_SECRET_KEY'], 
                algorithm="HS256"
            )
            
            return {
                'token': token,
                'role': role_name,
                'created_on': payload['created_on'],
                'message': 'Third Party Token created successfully'
            }, 200
            
        except Exception as err:
            logger = logging.getLogger("pyautomation")
            logger.error(f"Error creating TPT: {str(err)}")
            return {'message': f'Error creating token: {str(err)}'}, 500