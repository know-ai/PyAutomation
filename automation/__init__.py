import os
import pytz
from pathlib import Path
from flask import Flask, send_from_directory, send_file
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

# Ruta del frontend React construido
# Buscar en múltiples ubicaciones: primero en el paquete instalado, luego en desarrollo local
def _find_hmi_dist_path():
    """Busca el directorio HMI dist en múltiples ubicaciones."""
    # 1. Intentar en la ubicación del paquete instalado (automation/hmi/)
    try:
        import pkg_resources
        # Buscar el directorio hmi dentro del paquete automation
        hmi_dir = pkg_resources.resource_filename('automation', 'hmi')
        if os.path.exists(hmi_dir) and os.path.exists(os.path.join(hmi_dir, 'index.html')):
            return hmi_dir
    except (ImportError, Exception):
        pass
    
    # 2. Intentar usando importlib.resources (Python 3.9+)
    try:
        import importlib.resources as pkg_resources
        try:
            # Intentar acceder al directorio hmi como recurso
            hmi_files = pkg_resources.files('automation') / 'hmi'
            if hmi_files.is_dir() and (hmi_files / 'index.html').exists():
                # Para obtener la ruta del sistema de archivos
                with pkg_resources.path('automation', 'hmi') as hmi_path:
                    if hmi_path.exists() and (hmi_path / 'index.html').exists():
                        return str(hmi_path)
        except (ModuleNotFoundError, FileNotFoundError, AttributeError):
            pass
    except ImportError:
        pass
    
    # 3. Intentar en la ubicación relativa al archivo actual (paquete instalado)
    current_file = Path(__file__).parent
    package_hmi_path = current_file / "hmi"
    if package_hmi_path.exists() and (package_hmi_path / "index.html").exists():
        return str(package_hmi_path)
    
    # 4. Intentar en la ubicación local (desarrollo)
    local_path = os.path.join(".", "hmi", "dist")
    if os.path.exists(local_path) and os.path.exists(os.path.join(local_path, "index.html")):
        return local_path
    
    return None

HMI_DIST_PATH = _find_hmi_dist_path()


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
            
            # Configurar rutas para servir el frontend React
            self._setup_frontend_routes(app)
            
            return app
    
    def _setup_frontend_routes(self, app):
        """
        Configura las rutas para servir el frontend React construido en /hmi.
        Sirve archivos estáticos y redirige todas las rutas bajo /hmi al index.html (SPA routing).
        Estas rutas se registran con baja prioridad para no interferir con Dash y la API.
        """
        # Verificar si existe el directorio del frontend construido
        if not HMI_DIST_PATH or not os.path.exists(HMI_DIST_PATH):
            return  # Si no existe, no configuramos las rutas (modo desarrollo o sin frontend)
        
        # Servir archivos estáticos del frontend (JS, CSS, assets, etc.) bajo /hmi
        @app.route('/hmi/assets/<path:filename>')
        def serve_frontend_assets(filename):
            """Sirve archivos estáticos del frontend (JS, CSS, imágenes, etc.)"""
            assets_dir = os.path.join(HMI_DIST_PATH, 'assets')
            if os.path.exists(assets_dir):
                return send_from_directory(assets_dir, filename)
            return None
        
        # Ruta catch-all para SPA bajo /hmi: todas las rutas /hmi/* sirven el index.html
        @app.route('/hmi/', defaults={'path': ''})
        @app.route('/hmi/<path:path>')
        def serve_frontend_hmi(path):
            """
            Sirve el frontend React bajo /hmi.
            Para rutas que no sean archivos estáticos, sirve index.html (SPA routing).
            """
            # Intentar servir el archivo estático si existe
            if path:
                file_path = os.path.join(HMI_DIST_PATH, path)
                if os.path.exists(file_path) and os.path.isfile(file_path):
                    return send_from_directory(HMI_DIST_PATH, path)
            
            # Para todas las demás rutas bajo /hmi, servir index.html (SPA routing)
            index_path = os.path.join(HMI_DIST_PATH, 'index.html')
            if os.path.exists(index_path):
                return send_file(index_path)
            
            return None
        
__application = CreateApp()
server = __application()    
server.config['AUTOMATION_APP_SECRET_KEY'] = AUTOMATION_APP_SECRET_KEY
server.config['AUTOMATION_SUPERUSER_PASSWORD'] = AUTOMATION_SUPERUSER_PASSWORD
server.config['BUNDLE_ERRORS'] = True
opcua_server = OPCUAServer()
