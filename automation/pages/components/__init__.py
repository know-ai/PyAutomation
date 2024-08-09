import dash
import dash_bootstrap_components as dbc

def page_title(title:str):

    return dash.html.H1(title)

def modal_error(title:str, modal_id:str, button_close_id:str, body_id:str):

    return dash.html.Div(
        [
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle(title), close_button=True),
                    dbc.ModalBody("This modal is vertically centered", id=body_id),
                    dbc.ModalFooter(
                        dbc.Button(
                            "Close",
                            id=button_close_id,
                            className="ms-auto",
                            n_clicks=0,
                        )
                    ),
                ],
                id=modal_id,
                centered=True,
                is_open=False,
            ),
        ]
    )

def modal_confirm(title:str, modal_id:str, body_id:str, yes_button_id:str, no_button_id:str):

    return dash.html.Div(
        [
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle(title), close_button=True),
                    dbc.ModalBody("This modal is vertically centered", id=body_id),
                    dbc.ModalFooter(
                        [
                            dbc.Button(
                                "Yes",
                                id=yes_button_id,
                                className="ms-auto",
                                n_clicks=0,
                            ),
                            dbc.Button(
                                "No",
                                id=no_button_id,
                                className="ms-auto",
                                n_clicks=0,
                            )
                        ]
                    ),
                ],
                id=modal_id,
                centered=True,
                is_open=False,
            ),
        ]
    )


def navbar():
    return dbc.NavbarSimple(
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