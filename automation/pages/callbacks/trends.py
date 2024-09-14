import dash
import plotly.graph_objects as go
from math import ceil
from automation.tags import CVTEngine

cvt = CVTEngine()


def init_callback(app:dash.Dash):

    @app.callback(
        dash.Output('trends_tags_dropdown', 'options'),
        dash.Input('trends_page', 'pathname'),
        prevent_initial_call=True
        )
    def display_page(pathname):
        r"""
        Documentation here
        """
        
        if pathname=="/trends":
                
            tags_options = [tag["name"] for tag in app.automation.cvt.get_tags()]
            
            return tags_options
        
        return dash.no_update
    
    @app.callback(
        dash.Output('trends_cvt_datatable', 'data'),
        dash.Output('trends_figure', 'figure'),
        dash.Input('timestamp-interval', 'n_intervals'),
        dash.State('trends_tags_dropdown', 'value'),
        prevent_initial_call=True
        )
    def tags(n_intervals, values):
        r"""
        Documentation here
        """
        if values:

            fig = go.Figure()
            counter_axis = 0
            labels = dict()
            data = list()
            units = list()
            
            for tag_name in values:

                timestamp = app.automation.das.buffer[tag_name]["timestamp"]
                values = app.automation.das.buffer[tag_name]["values"]
                unit = app.automation.das.buffer[tag_name]["unit"]

                current_value = values.current()
                if current_value:
                    data.append({
                        "tag": tag_name, "value": f"{current_value} {unit}"
                    })

                if unit not in units:
                    counter_axis += 1
                    units.append(unit)

                if counter_axis==1:

                    fig.add_trace(go.Scatter(x=timestamp, y=values, name=tag_name))
                    labels["yaxis"] =  {
                            "title": unit
                        }
                else:

                    fig.add_trace(go.Scatter(x=timestamp, y=values, name=tag_name, yaxis=f"y{counter_axis}"))
                    labels[f"yaxis{counter_axis}"] = {
                            "title": unit,
                            "anchor": "free",
                            "overlaying": "y",
                            "autoshift": True
                        }            

            fig.update_layout(**labels)

            return data, fig
        
        return dash.no_update, dash.no_update
    

    @app.callback(
        dash.Input('trends_last_values_dropdown', 'value'),
        prevent_initial_call=True
        )
    def last_values(last_values):
        r"""
        Documentation here
        """
        
        for tag_name, _ in app.automation.das.buffer.items():

            # COMPUTATION OF MAX LENGTH OF THE BUFFER
            buffer_size = get_buffer_size(tag_name=tag_name, last_values=last_values)            
            app.automation.das.buffer[tag_name]["timestamp"].size = buffer_size
            app.automation.das.buffer[tag_name]["values"].size = buffer_size

    def get_buffer_size(tag_name:str, last_values:int):
        r"""
        Documentation here
        """
        tag = cvt.get_tag_by_name(name=tag_name)
        scan_time = tag.get_scan_time() # Milliseconds
        
        if not scan_time:
            
            current_timestamp = app.automation.das.buffer[tag_name]["timestamp"].current()
            previous_last = app.automation.das.buffer[tag_name]["timestamp"].previous_current()
            dt = current_timestamp - previous_last
            return ceil(last_values / dt.seconds)
        
        scan_time = scan_time / 1000
        return ceil(last_values / scan_time)
        