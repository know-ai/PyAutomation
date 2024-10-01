import dash
import dash_bootstrap_components as dbc
from automation.pages.components import Components
from automation.pages.components.alarms import AlarmsComponents

dash.register_page(__name__)

layout = dbc.Container(
    [   
        dbc.Breadcrumb(
            items=[
                {"label": "Home", "href": "/"},
                {"label": "Alarms", "active": True},
            ],
        ),
        Components.modal_error(
            title="Error",
            modal_id="modal-alarm-create",
            button_close_id="close-model-alarm-create",
            body_id="modal-body-alarm-create"
        ),
        Components.modal_confirm(
            title="Confirmation",
            modal_id="modal-update-delete-alarm",
            body_id="modal-update-delete-alarm-body",
            yes_button_id="update-delete-alarm-yes",
            no_button_id="update-delete-alarm-no"
        ),
        AlarmsComponents.create_alarm_form(),
        AlarmsComponents.alarms_table()
    ],
    fluid=False,
    className="my-3"
)