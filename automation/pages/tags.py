import dash
from automation.pages.components import page_title
from automation.pages.components.tags import modal, modal_delete_update, create_tag_form, tags_table

layout = dash.html.Div([
    page_title('Tags'),
    create_tag_form,
    tags_table,
    modal,
    modal_delete_update
])