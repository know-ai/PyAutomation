import dash
import dash_bootstrap_components as dbc

class AlarmSummaryComponents:

    @classmethod
    def alarm_summary_table(cls)->dash.dash_table.DataTable:
        r"""
        Documentation here
        """
        return dbc.Container(
            dbc.Row(
                dbc.Col(
                    dash.dash_table.DataTable(
                        data=[],
                        columns=[
                            {'name': 'id', 'id': 'id', 'editable': False}, 
                            {'name': 'name', 'id': 'name', 'editable': False}, 
                            {'name': 'tag', 'id': 'tag', 'editable': False}, 
                            {'name': 'description', 'id': 'description', 'editable': False}, 
                            {'name': 'state', 'id': 'state', 'editable': False}, 
                            {'name': 'alarm_time', 'id': 'alarm_time', 'editable': False}, 
                            {'name': 'ack_time', 'id': 'ack_time', 'editable': False}
                        ],
                        id="alarms_summary_datatable",
                        filter_action="native",
                        sort_action="native",
                        sort_mode="multi",
                        selected_columns=[],
                        page_action="native",
                        page_current= 0,
                        page_size= 10,
                        persistence=True,
                        editable=True,
                        persisted_props=['data'],
                        export_format='xlsx',
                        export_headers='display',
                        style_table={'overflowX': 'auto'},
                    ),
                    width=12,
                )
            ),
            fluid=True,
            className="mx-0 px-0"
        )