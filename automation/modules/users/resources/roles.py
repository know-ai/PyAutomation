from flask_restx import Namespace, Resource
from .... import PyAutomation
from ....modules.users.roles import roles
from ....extensions.api import api
from ....extensions import _api as Api
from .models.roles import create_role_parser


ns = Namespace('Roles', description='Role Management')
app = PyAutomation()

@ns.route('/')
class UsersByRoleResource(Resource):

    @api.doc(security='apikey', description="Retrieves a list of all defined roles.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    def get(self):
        """
        Get all roles.

        Retrieves a list of all user roles currently defined in the system.
        """

        return roles.serialize(), 200

@ns.route('/add')
class CreateRoleResource(Resource):
    
    @Api.validate_reqparser(reqparser=create_role_parser)
    @api.doc(security='apikey', description="Creates a new user role.")
    @api.response(200, "Role created successfully")
    @api.response(400, "Role creation failed")
    @Api.token_required(auth=True)
    @ns.expect(create_role_parser)
    def post(self):
        """
        Add Role.

        Creates a new role with the specified name and permission level.
        """  
        args = create_role_parser.parse_args()
        role, message = app.set_role(**args)
        
        if role:

            return role.serialize(), 200
        
        return message, 400