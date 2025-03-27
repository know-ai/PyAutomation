from math import ceil
import dash
from ...utils import find_differences_between_lists
import plotly.graph_objects as go
from ...tags import CVTEngine

cvt = CVTEngine()


def init_callback(app:dash.Dash):

    @app.callback(
        dash.Output('filter_tags_dropdown', 'options'),
        dash.Input('filter_page', 'pathname'),
        prevent_initial_call=True
        )
    def display_page(pathname):
        r"""
        Documentation here
        """
        if pathname=="/filter":
                
            tags_options = [tag["name"] for tag in app.automation.cvt.get_tags()]
            
            return tags_options
        
        return dash.no_update
    
    @app.callback(
        dash.Output('filter_trends_figure', 'figure'),
        dash.Input('timestamp-interval', 'n_intervals'),
        dash.State('filter_tags_dropdown', 'value'),
        prevent_initial_call=True
        )
    def fig_tags(n_intervals, values):
        r"""
        Documentation here
        """
        if values:

            fig = go.Figure()
            counter_axis = 0
            labels = dict()
            units = list()
            
            for tag_name in values:

                timestamp = app.automation.das.buffer[tag_name]["timestamp"]
                values = app.automation.das.buffer[tag_name]["values"]
                unit = app.automation.das.buffer[tag_name]["unit"]

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

            return fig
        
        return dash.no_update
    

    @app.callback(
        dash.Output('filter_cvt_datatable', 'data', allow_duplicate=True),
        dash.Input('filter_page', 'pathname'),
        dash.Input('filter_tags_dropdown', 'value'),
        prevent_initial_call=True
        )
    def data_tags(pathname, values):
        r"""
        Documentation here
        """
        if values:

            data = list()
            for tag_name in values:

                tag = app.automation.cvt.get_tag_by_name(name=tag_name)

                data.append({
                    "id": tag.id,
                    "display_name": tag.display_name, 
                    "gaussian_filter": tag.gaussian_filter,
                    "threshold": tag.gaussian_filter_threshold,
                    "R-value": tag.gaussian_filter_r_value * 100.0
                })      

            return data
        
        return dash.no_update
    

    @app.callback(
        dash.Input('filter_last_values_dropdown', 'value'),
        dash.State('filter_tags_dropdown', 'value'),
        prevent_initial_call=True
        )
    def last_values(last_values, tags):
        r"""
        Documentation here
        """
        for tag_name in tags:

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
            return ceil(last_values / dt.total_seconds())
        
        scan_time = scan_time / 1000
        return ceil(last_values / scan_time)
    

    @app.callback(
        dash.Output('filter_cvt_datatable', 'data'), 
        dash.Input('filter_cvt_datatable', 'data_timestamp'),
        dash.State('filter_cvt_datatable', 'data_previous'),
        dash.State('filter_cvt_datatable', 'data'),
        dash.State('filter_tags_dropdown', 'value'),
        )
    def update_tags(timestamp, previous, current, tags):
        
        message = None

        if timestamp:
            
            data = list()
            to_updates = find_differences_between_lists(previous, current)
            tag_to_update = to_updates[0]
            tag_id = tag_to_update.pop("id")
            
            if message:
                
                dash.set_props("modal-error-filter-tags-body", {"children": message})
                dash.set_props("modal-error-filter-tags", {'is_open': True})
                for tag_name in tags:

                    tag = app.automation.cvt.get_tag_by_name(name=tag_name)

                    data.append({
                        "id": tag.id,
                        "display_name": tag.display_name, 
                        "gaussian_filter": tag.gaussian_filter,
                        "threshold": tag.gaussian_filter_threshold,
                        "R-value": tag.gaussian_filter_r_value * 100.0
                    }) 
                
                return data

            if "segment" in tag_to_update:

                manufacturer_segment = tag_to_update['segment'].split("->")
                manufacturer = manufacturer_segment[0]
                segment = manufacturer_segment[1]
                tag_to_update.update({
                    "segment": segment,
                    "manufacturer": manufacturer
                })
            
            tag, message = app.automation.update_tag(id=tag_id, **tag_to_update)
            
            if not tag:

                dash.set_props("modal-error-filter-tags-body", {"children": message})
                dash.set_props("modal-error-filter-tags", {'is_open': True})
            
        for tag_name in tags:

            tag = app.automation.cvt.get_tag_by_name(name=tag_name)

            data.append({
                "id": tag.id,
                "display_name": tag.display_name, 
                "gaussian_filter": tag.gaussian_filter,
                "threshold": tag.gaussian_filter_threshold,
                "R-value": tag.gaussian_filter_r_value * 100.0
            }) 
        
        return data

    @app.callback(
        dash.Output("modal-update-filter-tags", "is_open"),
        dash.Input("close-modal-update-filter-tags", "n_clicks"),
        [dash.State("modal-update-filter-tags", "is_open")],
    )
    def close_error_button(n, is_open):
        r"""
        Documentation here
        """
        if n:

            return not is_open
        
        return is_open
    
    @app.callback(
        dash.Output("modal-success-filter-tags", "is_open"),
        dash.Input("close-modal-success-filter-tags", "n_clicks"),
        [dash.State("modal-success-filter-tags", "is_open")],
    )
    def close_success_button(n, is_open):
        r"""
        Documentation here
        """
        if n:

            return not is_open
        
        return is_open