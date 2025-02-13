import dash
import dash_bootstrap_components as dbc

class OPCUAServerComponents:

    @classmethod
    def opcua_server_table(cls)->dash.dash_table.DataTable:
        r"""
        Documentation here
        """
        return dbc.Container(   
            dbc.Row(
                dbc.Col(
                    dash.dash_table.DataTable(
                        data=[],
                        columns=[
                            {'name': 'name', 'id': 'name', 'editable': False}, 
                            {'name': 'namespace', 'id': 'namespace', 'editable': False}, 
                            {'name': 'access type', 'id': 'access_type', 'presentation': 'dropdown', 'clearable': False}
                        ],
                        id="opcua_server_datatable",
                        filter_action="native",
                        sort_action="native",
                        sort_mode="multi",
                        row_deletable=True,
                        selected_columns=[],
                        dropdown = {
                            'access_type': {
                                'options': [
                                    {'label': 'Read', 'value': 'Read'},
                                    {'label': 'ReadWrite', 'value': 'ReadWrite'},
                                    {'label': 'Write', 'value': 'Write'}
                                ],
                                'clearable': False
                            }
                        },
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
            className="mx-0 px-0",
            
        )