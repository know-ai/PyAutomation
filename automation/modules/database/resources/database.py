from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api

ns = Namespace('Database', description='Database Configuration and Connection Management')
app = PyAutomation()

# Modelo para la configuración de conexión a la base de datos
db_connect_model = api.model("db_connect_model", {
    'dbtype': fields.String(required=True, description='Database type: sqlite, mysql, or postgresql'),
    'dbfile': fields.String(required=False, description='Database filename (for SQLite only)'),
    'user': fields.String(required=False, description='Database user (for MySQL/PostgreSQL)'),
    'password': fields.String(required=False, description='Database password (for MySQL/PostgreSQL)'),
    'host': fields.String(required=False, description='Database host (for MySQL/PostgreSQL)'),
    'port': fields.Integer(required=False, description='Database port (for MySQL/PostgreSQL)'),
    'name': fields.String(required=False, description='Database name (for MySQL/PostgreSQL)'),
    'reload': fields.Boolean(required=False, default=False, description='Reload tags into machine after connection')
})

@ns.route('/config')
class DatabaseConfigResource(Resource):

    # @api.doc(security='apikey', description="Retrieves the current database configuration.")
    @api.doc(security=None, description="Retrieves the current database configuration.")
    @api.response(200, "Success")
    @api.response(404, "Configuration not found")
    # @Api.token_required(auth=True)
    def get(self):
        r"""
        Get database configuration.

        Retrieves the current database configuration from db_config.json.
        """
        config = app.get_db_config()
        if config:
            return config, 200
        return {"message": "Database configuration not found"}, 404

@ns.route('/connected')
class DatabaseConnectedResource(Resource):

    @api.doc(security='apikey', description="Checks if the database is currently connected.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    def get(self):
        r"""
        Check database connection status.

        Returns whether the database is currently connected.
        """
        is_connected = app.is_db_connected()
        return {"connected": is_connected}, 200

@ns.route('/connect')
class DatabaseConnectResource(Resource):

    # @api.doc(security='apikey', description="Connects to the database with the provided configuration.")
    @api.doc(security=None, description="Connects to the database with the provided configuration.")
    @api.response(200, "Connection successful")
    @api.response(400, "Connection failed")
    # @Api.token_required(auth=True)
    @ns.expect(db_connect_model)
    def post(self):
        r"""
        Connect to database.

        Sets the database configuration and establishes a connection.
        For SQLite, only 'dbtype' and 'dbfile' are required.
        For MySQL/PostgreSQL, 'dbtype', 'user', 'password', 'host', 'port', and 'name' are required.
        """
        try:
            # Extraer parámetros del payload
            dbtype = api.payload.get('dbtype', 'sqlite')
            dbfile = api.payload.get('dbfile', 'app.db')
            user = api.payload.get('user')
            password = api.payload.get('password')
            host = api.payload.get('host', '127.0.0.1')
            port = api.payload.get('port', 5432)
            name = api.payload.get('name', 'app_db')
            reload = api.payload.get('reload', False)

            # Validar parámetros según el tipo de base de datos
            if dbtype.lower() == 'sqlite':
                # Para SQLite solo necesitamos dbtype y dbfile
                app.set_db_config(
                    dbtype=dbtype,
                    dbfile=dbfile
                )
            elif dbtype.lower() in ['mysql', 'postgresql']:
                # Para MySQL/PostgreSQL necesitamos todos los parámetros
                if not user or not password or not name:
                    return {
                        "message": "For MySQL/PostgreSQL, 'user', 'password', and 'name' are required"
                    }, 400
                
                app.set_db_config(
                    dbtype=dbtype,
                    user=user,
                    password=password,
                    host=host,
                    port=port,
                    name=name
                )
            else:
                return {
                    "message": f"Invalid database type: {dbtype}. Supported types: sqlite, mysql, postgresql"
                }, 400

            # Conectar a la base de datos
            success = app.connect_to_db(reload=reload)
            
            if success:
                return {
                    "message": "Database connected successfully",
                    "connected": True
                }, 200
            else:
                return {
                    "message": "Failed to connect to database",
                    "connected": False
                }, 400

        except Exception as e:
            return {
                "message": f"Error connecting to database: {str(e)}",
                "connected": False
            }, 400

@ns.route('/disconnect')
class DatabaseDisconnectResource(Resource):

    @api.doc(security='apikey', description="Disconnects from the database.")
    @api.response(200, "Disconnection successful")
    @Api.token_required(auth=True)
    def post(self):
        r"""
        Disconnect from database.

        Closes the database connection and stops history logging.
        """
        try:
            app.disconnect_to_db()
            return {
                "message": "Database disconnected successfully",
                "connected": False
            }, 200
        except Exception as e:
            return {
                "message": f"Error disconnecting from database: {str(e)}"
            }, 400

