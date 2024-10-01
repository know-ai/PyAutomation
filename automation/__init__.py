from flask import Flask
from automation.core import PyAutomation


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
server.config['TPT_TOKEN'] = '073821603fcc483f9afee3f1500782a4'
