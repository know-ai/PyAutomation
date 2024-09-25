from flask_restx import Namespace, Resource
from automation import PyAutomation


ns = Namespace('Tags', description='Tags')
app = PyAutomation()


@ns.route('/')
class TagsCollection(Resource):

    def get(self):
        """
        Get Tags
        """
        return app.get_tags(), 200 