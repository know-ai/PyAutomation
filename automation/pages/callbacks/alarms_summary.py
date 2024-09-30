import dash

def init_callback(app:dash.Dash):

    @app.callback(
        dash.Output('alarms_summary_datatable', 'data'),
        dash.Input('alarms_history_page', 'pathname'),
        prevent_initial_call=True
        )
    def display_page(pathname):
        r"""
        Documentation here
        """
        if pathname=="/alarms-history":

            data = app.automation.get_lasts_alarms()

            return data
        
        return dash.no_update