import dash
from automation.pages.components import Components
from automation.pages.components.database import DatabaseComponents

dash.register_page(__name__)

layout = dash.html.Div([
    Components.page_title('Database'),
    DatabaseComponents.create_db_config_form()
])