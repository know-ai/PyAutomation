from flask_restx import Namespace, Resource, fields
from automation import PyAutomation
from automation.extensions.api import api
from automation.extensions import _api as Api
from automation.modules.users.users import users


ns = Namespace('Users', description='Users')
app = PyAutomation()



login_model = api.model("login_model", {
    'username': fields.String(required=False, description='Username'),
    'email': fields.String(required=False, description='Email'),
    'password': fields.String(required=True, description='Password')
})

signup_model = api.model("signup_model", {
    'username': fields.String(required=True, description='Username'),
    'role_name': fields.String(required=True, description="Role ['operator', 'supervisor', 'admin', 'auditor']"),
    'email': fields.String(required=True, description='Email address'),
    'password': fields.String(required=True, description='Password'),
    'name': fields.String(required=False, description='User`s name'),
    'lastname':fields.String(required=False, description='User`s last name')
})


@ns.route('/signup')
class SignUpResource(Resource):
    
    @ns.expect(signup_model)
    def post(self):
        """User signup"""
        user, message = users.signup(**api.payload)
        
        if user:

            return user.serialize(), 200
        
        return message, 400


@ns.route('/login')
class LoginResource(Resource):


    @ns.expect(login_model)
    def post(self):
        """User login"""
        user = users.login(**api.payload)

        if user:

            return {
                "apiKey": user.token,
                "role": user.role.name,
                "role_level": user.role.level
                }, 200

        return {"message": "Credentials Fail"}, 403