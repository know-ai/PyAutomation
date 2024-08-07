import dash
import dash_bootstrap_components as dbc
import pandas as pd


class ConfigView(dash.Dash):
    r"""
    Documentation here
    """

    def __init__(self, **kwargs):
    
        super().__init__(__name__, **kwargs)

        navbar = dbc.NavbarSimple(
            children=[
                dbc.NavItem(dbc.NavLink("Monitor", href="/")),
                dbc.NavItem(dbc.NavLink("Database", href="/database")),
                dbc.DropdownMenu(
                    children=[
                        dbc.DropdownMenuItem("Tags", header=True),
                        dbc.DropdownMenuItem("Definition", href="/tags", id="tags_definition_link"),
                        dbc.DropdownMenuItem("Trends", href="/trends"),
                    ],
                    nav=True,
                    in_navbar=True,
                    label="Tags",
                ),
                dbc.DropdownMenu(
                    children=[
                        dbc.DropdownMenuItem("Alarms", header=True),
                        dbc.DropdownMenuItem("Definition", href="/alarms"),
                        dbc.DropdownMenuItem("History", href="/alarms-history"),
                    ],
                    nav=True,
                    in_navbar=True,
                    label="Alarms",
                )
            ],
            brand="PyAutomation Configuration",
            color="primary",
            dark=True,
        )
        self.layout = dash.html.Div([
            navbar,
            dash.page_container
        ])

    def set_automation_app(self, automation_app):

        self.automation = automation_app
        
    def tags_table_data(self):

        tags = pd.DataFrame(self.automation.cvt.get_tags())
        columns_allowed = ["id", "name", "unit", "data_type", "description", "display_name", "opcua_address", "node_namespace"]
        records=tags.to_dict("records")
        data = list()
        for record in records:
            
            data.append({ key : value for (key, value) in record.items() if key in columns_allowed })

        return data