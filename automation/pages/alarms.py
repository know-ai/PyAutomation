import dash
from automation.pages.components import Components
from automation.pages.components.alarms import AlarmsComponents

dash.register_page(__name__)

layout = dash.html.Div([
    Components.page_title('Alarms'),
    AlarmsComponents.create_alarm_form(),
    AlarmsComponents.alarms_table()
])