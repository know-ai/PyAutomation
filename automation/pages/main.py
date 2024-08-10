import dash
from automation.pages.components import Components


class ConfigView(dash.Dash):
    r"""
    Documentation here
    """

    def __init__(self, **kwargs):
    
        super(ConfigView, self).__init__(__name__, suppress_callback_exceptions=True, **kwargs)
        
        self.layout = dash.html.Div([
            Components.navbar(),
            dash.page_container
        ])

    def set_automation_app(self, automation_app):

        self.automation = automation_app
        
    def tags_table_data(self):

        return self.automation.cvt.get_tags()