import dash
from automation.pages.components import navbar


class ConfigView(dash.Dash):
    r"""
    Documentation here
    """

    def __init__(self, **kwargs):
    
        super(ConfigView, self).__init__(__name__, **kwargs)

        self.layout = dash.html.Div([
            navbar(),
            dash.page_container
        ])

    def set_automation_app(self, automation_app):

        self.automation = automation_app
        
    def tags_table_data(self):

        return self.automation.cvt.get_tags()