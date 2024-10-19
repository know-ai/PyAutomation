import dash
import dash_bootstrap_components as dbc
from automation.pages.components import Components
from automation.pages.components.tags import TagsComponents

dash.register_page(__name__)

layout = dbc.Container(
    [
        dbc.Breadcrumb(
            items=[
                {"label": "Home", "href": "/"},
                {"label": "Tags", "active": True},
            ],
        ),
        Components.modal_error(
            title="Error",
            modal_id="modal-centered",
            button_close_id="close-centered",
            body_id="modal-body"
        ),
        Components.modal_error(
            title="Success",
            modal_id="modal-success",
            button_close_id="close-success",
            body_id="modal-success-body"
        ),
        Components.modal_confirm(
            title="Confirmation",
            modal_id="modal-update_delete-centered",
            body_id="modal-update-delete-tag-body",
            yes_button_id="update-delete-tag-yes",
            no_button_id="update-delete-tag-no"
        ),
        TagsComponents.create_tag_form(),
        TagsComponents.tags_table()
    ],
    fluid=False,
    className="my-3"
)