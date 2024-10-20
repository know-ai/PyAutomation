import dash
from ..pages.components import Components


class ConfigView(dash.Dash):
    r"""
    Documentation here
    """

    def __init__(self, **kwargs):
    
        super(ConfigView, self).__init__(__name__, suppress_callback_exceptions=True, **kwargs)
        
        self.layout = dash.html.Div([
            dash.dcc.Interval(id='timestamp-interval', interval=1000, n_intervals=0),
            Components.navbar(),
            dash.page_container
        ])

    def set_automation_app(self, automation_app):

        self.automation = automation_app
        
    def tags_table_data(self):
    
        tags = list()

        for tag in self.automation.get_tags():
            tag.update({
                "segment": f"{tag['manufacturer']}->{tag['segment']}"
            })
            tags.append(tag)        

        return tags
    
    def alarms_table_data(self):
        data = [{
                "id": alarm["identifier"],
                "tag": alarm["tag"], 
                "name": alarm["name"],
                "description": alarm["description"],
                "state": alarm["state"]["state"],
                "alarm_type": alarm["alarm_setpoint"]["type"],
                "trigger_value": alarm["alarm_setpoint"]["value"],
                } for alarm in self.automation.alarm_manager.serialize()]

        return data
    
    def machines_table_data(self):

        data = [{
                "name": machine["name"],
                "sampling_time": machine["machine_interval"], 
                "description": machine["description"],
                "state": machine["state"],
                "criticity": machine["criticity"],
                "priority": machine["priority"],
                "classification": machine["classification"],
                } for machine in self.automation.machine_manager.serialize_machines()]

        return data