import dash
from automation.pages.components import page_title, modal_error, modal_confirm
from automation.pages.components.tags import create_tag_form, tags_table

dash.register_page(__name__)

layout = dash.html.Div([
    modal_error(
        title="Error",
        modal_id="modal-centered",
        button_close_id="close-centered",
        body_id="modal-body"
    ),
    modal_confirm(
        title="Confirmation",
        modal_id="modal-update_delete-centered",
        body_id="modal-update-delete-tag-body",
        yes_button_id="update-delete-tag-yes",
        no_button_id="update-delete-tag-no"
    ),
    page_title('Tags'),
    create_tag_form,
    tags_table
])