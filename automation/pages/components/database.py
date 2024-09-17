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
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                dbc.InputGroup(
                                                    [
                                                        dbc.Input(placeholder="DB Name", id="db_name_input")
                                                    ], 
                                                    size="md"
                                                )
                                            ],
                                            width=12,
                                            className="col-sm-12 col-md-2"
                                        ),

                                        dbc.Col(
                                            [
                                                dbc.InputGroup(
                                                    [
                                                        dbc.Input(placeholder="DB Host", id="db_host_input")
                                                    ], 
                                                    size="md"
                                                )
                                            ],
                                            width=12,
                                            className="col-sm-12 col-md-2"
                                        ),

                                        dbc.Col(
                                            [
                                                dbc.InputGroup(
                                                    [
                                                        dbc.Input(placeholder="DB Port", id="db_port_input")
                                                    ], 
                                                    size="md"
                                                )
                                            ],
                                            width=12,
                                            className="col-sm-12 col-md-2"
                                        ),

                                        dbc.Col(
                                            [
                                                dbc.InputGroup(
                                                    [
                                                        dbc.Input(placeholder="DB User", id="db_user_input")
                                                    ], 
                                                    size="md"
                                                )
                                            ],
                                            width=12,
                                            className="col-sm-12 col-md-3"
                                        ),

                                        dbc.Col(
                                            [
                                                dbc.InputGroup(
                                                    [
                                                        dbc.Input(placeholder="DB Password", id="db_password_input")
                                                    ], 
                                                    size="md")
                                            ],
                                            width=12,
                                            className="col-sm-12 col-md-3"
                                        ),

                                        dbc.Col(
                                            dbc.Button(
                                                "Create DB",
                                                color="primary",
                                                outline=True,
                                                disabled=True,
                                                id="create_db_button",
                                                className="w-100"
                                            ),
                                            width="auto",
                                            className="d-flex justify-content-center align-items-center"
                                        ),
                                    ],
                                    className="form g-3" 
                                ),
                            ],
                            title="Connection Settings",
                            className="my-3"
                        )
                    ],
                start_collapsed=False,
                )
            ]
        )
