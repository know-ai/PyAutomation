import dash
import dash_bootstrap_components as dbc

class DatabaseComponents:

    @classmethod
    def create_db_config_form(cls):
        r"""
        Documentation here
        """
        return dash.html.Div(
            [
                dash.dcc.Location(id='database_page', refresh=False),
                dbc.Accordion(
                [
                    dbc.AccordionItem(
                        [
                            dbc.Row([
                                dbc.Col([
                                    dbc.InputGroup([dbc.Input(placeholder="DB Name", id="db_name_input")], size="md")
                                ],
                                width=3),
                                dbc.Col([
                                    dbc.InputGroup([dbc.Input(placeholder="DB Host", id="db_host_input")], size="md")
                                ],
                                width=2),
                                dbc.Col([
                                    dbc.InputGroup([dbc.Input(placeholder="DB Port", id="db_port_input")], size="md")
                                ],
                                width=3),
                                dbc.Col([
                                    dbc.InputGroup([dbc.Input(placeholder="DB User", id="db_user_input")], size="md")
                                ],
                                width=2),
                                dbc.Col([
                                    dbc.InputGroup([dbc.Input(placeholder="DB Password", id="db_password_input")], size="md")
                                ],
                                width=2)
                            ]),
                            dbc.Button("Create DB", color="primary", outline=True, disabled=True, id="create_db_button"),
                        ],
                        title="Connection Settings",
                    )
                ],
                start_collapsed=False,
                )
            ]
        )
