import dash
import dash_bootstrap_components as dbc
from automation.pages.components.trends import TrendsComponents


dash.register_page(__name__)



layout = dash.html.Div(
        [
            dash.dcc.Location(id='trends_page', refresh=False),
            dbc.Row(
                [
                    dbc.Col(dash.html.H1("Trends"), width=2)
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(TrendsComponents.tags(), width=10),
                    dbc.Col(TrendsComponents.last_values(), width=2)
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(TrendsComponents.current_value_table(), width=2),
                    dbc.Col(TrendsComponents.plot(), width=10)
                ]
            )
        ]
    )