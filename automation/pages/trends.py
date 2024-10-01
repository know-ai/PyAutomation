import dash
import dash_bootstrap_components as dbc
from automation.pages.components.trends import TrendsComponents

dash.register_page(__name__)

layout = dbc.Container(
    [
        dbc.Breadcrumb(
            items=[
                {"label": "Home", "href": "/"},
                {"label": "Tags", "href": "/tags"},
                {"label": "Trends", "active": True},
            ],
        ),
        dash.dcc.Location(id='trends_page', refresh=False),
        dbc.Row(
            [
                dbc.Col(TrendsComponents.tags(), width=6, className="col-sm-6 col-md-10"),
                dbc.Col(TrendsComponents.last_values(), width=6, className="col-sm-6 col-md-2 ps-0"),
            ],
            className="mb-3"
        ),
        dbc.Row(
            [
                dbc.Col(TrendsComponents.current_value_table(), width=12, className="col-sm-12 col-md-2 mb-2"),
                dbc.Col(TrendsComponents.plot(), width=12, className="col-sm-12 col-md-10"),
            ],
            className="mb-3"
        ),
    ],
    fluid=False,
    className="my-3"
)
    