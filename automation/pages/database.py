import dash

dash.register_page(__name__)

layout = dash.html.Div([
    dash.html.H1('Database')
])  