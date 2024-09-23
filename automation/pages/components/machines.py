import dash
import dash_bootstrap_components as dbc

class MachinesComponents:

    @classmethod
    def machines_table(cls)->dash.dash_table.DataTable:
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
                            {'name': 'sampling_time', 'id': 'sampling_time', 'editable': False}, 
                            {'name': 'description', 'id': 'description', 'editable': False}, 
                            {'name': 'state', 'id': 'state', 'editable': False}, 
                            {'name': 'criticity', 'id': 'criticity', 'editable': False}, 
                            {'name': 'priority', 'id': 'priority', 'editable': False},
                            {'name': 'classification', 'id': 'classification', 'editable': False},
                        ],
                        id="machines_datatable",
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