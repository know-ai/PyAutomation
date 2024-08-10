import dash
from automation.pages.components import Components
from automation.pages.components.tags import TagsComponents

dash.register_page(__name__)

layout = dash.html.Div([
    Components.modal_error(
        title="Error",
        modal_id="modal-centered",
        button_close_id="close-centered",
        body_id="modal-body"
    ),
    Components.modal_confirm(
        title="Confirmation",
        modal_id="modal-update_delete-centered",
        body_id="modal-update-delete-tag-body",
        yes_button_id="update-delete-tag-yes",
        no_button_id="update-delete-tag-no"
    ),
    Components.page_title('Tags'),
    TagsComponents.create_tag_form(),
    TagsComponents.tags_table()
])