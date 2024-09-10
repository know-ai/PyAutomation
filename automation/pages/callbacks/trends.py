import dash
import plotly.graph_objects as go
from automation.buffer import Buffer


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

            dropdown_options_tag = [tag["name"] for tag in app.automation.cvt.get_tags()]
            
            return dropdown_options_tag
        
        return dash.no_update
    
    @app.callback(
        dash.Output('trends_cvt_datatable', 'data'),
        dash.Output('trends_figure', 'figure'),
        dash.Input('timestamp-interval', 'n_intervals'),
        dash.State('trends_tags_dropdown', 'value'),
        dash.State('trends_last_values_dropdown', 'value'),
        prevent_initial_call=True
        )
    def tags(n_intervals, values, last_values):
        r"""
        Documentation here
        """
        if values:

            fig = go.Figure()

            tags_values = app.automation.cvt.get_values_by_name(values)
            data = list()
            units = list()
            labels = dict()
            
            if "timestamp" not in app.automation.das.buffer:

                app.automation.das.buffer['timestamp'] = Buffer(length=last_values)
            
            counter = 0
            counter_axis = 0
            
            for value in values:
                
                if counter==0:
                    
                    app.automation.das.buffer['timestamp'](value=tags_values[value]['timestamp'])
                
                counter += 1
                unit = tags_values[value]['unit']
                data.append({
                    "tag": value, "value": f"{tags_values[value]['value']} {tags_values[value]['unit']}"
                })

                if value not in app.automation.das.buffer:

                    app.automation.das.buffer[value] = Buffer(length=last_values)

                app.automation.das.buffer[value](value=tags_values[value]['value'])
                if unit not in units:
                    counter_axis += 1
                    units.append(unit)
                
                if counter_axis==1:
                    fig.add_trace(go.Scatter(x=app.automation.das.buffer["timestamp"], y=app.automation.das.buffer[value], name=value))
                    labels["yaxis"] =  {
                            "title": unit
                        }
                else:
                    fig.add_trace(go.Scatter(x=app.automation.das.buffer["timestamp"], y=app.automation.das.buffer[value], name=value, yaxis=f"y{counter_axis}"))
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
        
        for key, _ in app.automation.das.buffer.items():
            
            app.automation.das.buffer[key].max_length = last_values
        