from flask import Flask
from automation.core import PyAutomation
from automation.modules import Users, Roles, Role

DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"

app = Flask(__name__, instance_relative_config=False)

class CreateApp():
    """Initialize the core application."""


    def __call__(self):
        """
        Documentation here
        """
        app.client = None
        self.application = app
        
        with app.app_context():

            from automation import extensions
            extensions.init_app(app)

            from automation import modules
            modules.init_app(app)
            
            return app
        
__application = CreateApp()
server = __application()    
