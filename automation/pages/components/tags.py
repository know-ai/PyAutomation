import dash
import dash_bootstrap_components as dbc

modal = dash.html.Div(
    [
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("Error"), close_button=True),
                dbc.ModalBody("This modal is vertically centered", id="modal-body"),
                dbc.ModalFooter(
                    dbc.Button(
                        "Close",
                        id="close-centered",
                        className="ms-auto",
                        n_clicks=0,
                    )
                ),
            ],
            id="modal-centered",
            centered=True,
            is_open=False,
        ),
    ]
)


modal_delete_update = dash.html.Div(
    [
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("Header"), close_button=True),
                dbc.ModalBody("This modal is vertically centered", id="modal-update-delete-tag-body"),
                dbc.ModalFooter(
                    [
                        dbc.Button(
                            "Yes",
                            id="update-delete-tag-yes",
                            className="ms-auto",
                            n_clicks=0,
                        ),
                        dbc.Button(
                            "No",
                            id="update-delete-tag-no",
                            className="ms-auto",
                            n_clicks=0,
                        )
                    ]
                ),
            ],
            id="modal-update_delete-centered",
            centered=True,
            is_open=False,
        ),
    ]
)