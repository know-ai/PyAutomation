import os, pytz, secrets
from flask import Flask
from .core import PyAutomation
from .state_machine import OPCUAServer
from .modules.users.users import Users
from .modules.users.roles import Roles

app = Flask(__name__, instance_relative_config=False)

MANUFACTURER = os.environ.get('MANUFACTURER')
SEGMENT = os.environ.get('SEGMENT')
_TIMEZONE = os.environ.get('TIMEZONE') or "America/Caracas"
TIMEZONE = pytz.timezone(_TIMEZONE)
CERT_FILE = os.path.join(".", "ssl", os.environ.get('CERT_FILE') or "")
KEY_FILE = os.path.join(".", "ssl", os.environ.get('KEY_FILE') or "")
if not os.path.isfile(CERT_FILE):
    CERT_FILE = None

if not os.path.isfile(KEY_FILE):
    KEY_FILE = None
OPCUA_SERVER_PORT = os.environ.get('OPCUA_SERVER_PORT') or "53530"

def create_system_user():
    """
    Crea el usuario system si no existe
    """
    users = Users()
    roles = Roles()
    
    # Verificar si el usuario system existe
    if not users.check_username(username="system"):
        # Obtener el rol de administrador
        admin_role = roles.get_by_name(name="sudo")
        if admin_role:
            # Generar password e identificador dinámicamente
            system_password = secrets.token_urlsafe(32)
            system_identifier = secrets.token_hex(16)
            
            # Crear el usuario system
            user, message = users.signup(
                username="system",
                role_name="sudo",
                email="system@intelcon.com",
                password=system_password,
                name="System",
                lastname="Internal",
                identifier=system_identifier
            )

class CreateApp():
    """Initialize the core application."""

    def __call__(self):
        """
        Documentation here
        """
        app.client = None
        self.application = app
        
        with app.app_context():
            # Crear usuario system si no existe
            create_system_user()

            from . import extensions
            extensions.init_app(app)

            from . import modules
            modules.init_app(app)
            
            return app
        
__application = CreateApp()
server = __application()    
server.config['TPT_TOKEN'] = '073821603fcc483f9afee3f1500782a4'
server.config['BUNDLE_ERRORS'] = True
opcua_server = OPCUAServer()
