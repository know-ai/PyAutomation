from .api import Api
from .cors import Cors

_api = Api()
_cors = Cors()

def init_app(app):
    """
    Application extensions initialization.
    """
    # CORS first so preflight OPTIONS is handled before API/auth layers.
    extensions = (_cors, _api)

    for extension in extensions:
        
        extension.init_app(app)