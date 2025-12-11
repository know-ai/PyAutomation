import os, pytz
from flask import Flask
from .core import PyAutomation
from .state_machine import OPCUAServer

app = Flask(__name__, instance_relative_config=False)

MANUFACTURER = os.environ.get('AUTOMATION_MANUFACTURER')
SEGMENT = os.environ.get('AUTOMATION_SEGMENT')
_TIMEZONE = os.environ.get('AUTOMATION_TIMEZONE') or "America/Caracas"
TIMEZONE = pytz.timezone(_TIMEZONE)
CERT_FILE = os.path.join(".", "ssl", os.environ.get('AUTOMATION_CERT_FILE') or "")
KEY_FILE = os.path.join(".", "ssl", os.environ.get('AUTOMATION_KEY_FILE') or "")
if not os.path.isfile(CERT_FILE):
    CERT_FILE = None

if not os.path.isfile(KEY_FILE):
    KEY_FILE = None
AUTOMATION_OPCUA_SERVER_PORT = os.environ.get('AUTOMATION_OPCUA_SERVER_PORT') or "53530"
AUTOMATION_LOGGER_PERIOD = os.environ.get('AUTOMATION_LOGGER_PERIOD') or 10.0
AUTOMATION_APP_SECRET_KEY = os.environ.get('AUTOMATION_APP_SECRET_KEY') or "073821603fcc483f9afee3f1500782a4"
AUTOMATION_SUPERUSER_PASSWORD = os.environ.get('AUTOMATION_SUPERUSER_PASSWORD') or "super_ultra_secret_password"


class CreateApp():
    """Initialize the core application."""

    def __call__(self):
        """
        Documentation here
        """
        app.client = None
        self.application = app
        
        with app.app_context():

            from . import extensions
            extensions.init_app(app)

            from . import modules
            modules.init_app(app)
            
            return app
        
__application = CreateApp()
server = __application()    
server.config['AUTOMATION_APP_SECRET_KEY'] = AUTOMATION_APP_SECRET_KEY
server.config['AUTOMATION_SUPERUSER_PASSWORD'] = AUTOMATION_SUPERUSER_PASSWORD
server.config['BUNDLE_ERRORS'] = True
opcua_server = OPCUAServer()
