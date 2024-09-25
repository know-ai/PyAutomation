from flask import Flask
from automation.core import PyAutomation

DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"

server = Flask(__name__, instance_relative_config=False)

class CreateApp():
    """Initialize the core application."""


    def __call__(self):
        """
        Documentation here
        """
        server.client = None
        self.application = server
        
        with server.app_context():

            from automation import extensions
            extensions.init_app(server)

            from automation import modules
            modules.init_app(server)

            # try: # Importing factory extensions folder

            #     from . import extensions
            #     extensions.init_app(server)
            
            # except Exception as err:

            #     print(err)
            
            return server
