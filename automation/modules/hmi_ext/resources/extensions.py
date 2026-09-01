from flask_restx import Namespace, Resource

from automation.extensions import _api as Api
from automation.extensions.api import api
from automation.utils.hmi_extensions import list_menu_items

ns = Namespace("HMI", description="HMI shell extensions")


@ns.route("/extensions")
class HmiExtensionsResource(Resource):
    @api.doc(description="Sidebar entries registered by the product application.")
    @Api.token_required(auth=True)
    def get(self):
        return {"items": list_menu_items()}, 200
