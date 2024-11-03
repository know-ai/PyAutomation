from flask_restx import Namespace, Resource
from .... import PyAutomation
from ....modules.users.roles import roles
from ....extensions.api import api
from ....extensions import _api as Api
from .models.roles import create_role_parser


ns = Namespace('Roles', description='Roles')
app = PyAutomation()

@ns.route('/')
class UsersByRoleResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self):
        """View all tecnogiros's role"""

        return roles.serialize(), 200

@ns.route('/add')
class CreateRoleResource(Resource):
    
    @Api.validate_reqparser(reqparser=create_role_parser)
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(create_role_parser)
    def post(self):
        """Add Role"""  
        args = create_role_parser.parse_args()
        role, message = app.set_role(**args)
        
        if role:

            return role.serialize(), 200
        
        return message, 400