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
                            {'name': 'read_only', 'id': 'read_only', 'type': 'boolean'}
                        ],
                        id="opcua_server_datatable",
                        filter_action="native",
                        sort_action="native",
                        sort_mode="multi",
                        row_deletable=True,
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
            className="mx-0 px-0",
            
        )