from flask_cors import CORS
from automation.singleton import Singleton


class Cors(Singleton):

    def __init__(self):
        
        self.app = None

    def init_app(self, app):
        r"""
        Documentation here
        """

        self.app = CORS(app, resources={r"/*": {"origins": "*"}})

        return app