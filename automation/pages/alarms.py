import dash
from automation.pages.components import Components
from automation.pages.components.alarms import AlarmsComponents

dash.register_page(__name__)

layout = dash.html.Div([
    Components.page_title('Alarms'),
    Components.modal_error(
        title="Error",
        modal_id="modal-alarm-create",
        button_close_id="close-model-alarm-create",
        body_id="modal-body-alarm-create"
    ),
    Components.modal_confirm(
        title="Confirmation",
        modal_id="modal-update_delete-centered",
        body_id="modal-update-delete-tag-body",
        yes_button_id="update-delete-tag-yes",
        no_button_id="update-delete-tag-no"
    ),
    AlarmsComponents.create_alarm_form(),
    AlarmsComponents.alarms_table()
])