from flask_restx import Namespace, Resource
from .... import PyAutomation
from ....modules.users.roles import roles
from ....extensions.api import api
from ....extensions import _api as Api
from .models.roles import create_role_parser
import logging


ns = Namespace('Roles', description='Role Management')
app = PyAutomation()

@ns.route('/')
class UsersByRoleResource(Resource):

    @api.doc(security='apikey', description="Retrieves a list of all defined roles.")
    @api.response(200, "Success")
    @api.response(403, "Role not allowed")
    @api.response(503, "Authentication backend unavailable")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor", "sudo"])
    def get(self):
        """
        Get all roles.

        Retrieves a list of all user roles currently defined in the system.
        Uses the local catalog mirror when the historian is unavailable.
        """
        if not app.is_db_connected():
            try:
                from ....catalog.hydrate import fill_roles_from_local

                fill_roles_from_local()
            except Exception:
                logging.getLogger("pyautomation").debug(
                    "local catalog roles hydrate skipped",
                    exc_info=True,
                )

        return roles.serialize(), 200

@ns.route('/add')
class CreateRoleResource(Resource):
    
    @Api.validate_reqparser(reqparser=create_role_parser)
    @api.doc(security='apikey', description="Creates a new user role.")
    @api.response(200, "Role created successfully")
    @api.response(400, "Role creation failed")
    @api.response(403, "Role not allowed")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor", "sudo"])
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