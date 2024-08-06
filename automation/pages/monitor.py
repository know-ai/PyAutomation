import dash

dash.register_page(__name__, path="/")

layout = dash.html.Div([
    dash.html.H1('Monitor'),
    dash.html.Div([
        "Select a city: ",
        dash.dcc.RadioItems(
            options=['New York City', 'Montreal', 'San Francisco'],
            value='Montreal',
            id='analytics-input'
        )
    ]),
    dash.html.Br(),
    dash.html.Div(id='analytics-output'),
])


@dash.callback(
    dash.Output('analytics-output', 'children'),
    dash.Input('analytics-input', 'value')
)
def update_city_selected(input_value):
    return f'You selected: {input_value}'