import dash
import plotly.graph_objects as go

fig = go.Figure()

class FilterComponents:

    @classmethod
    def tags(cls)->dash.dcc.Dropdown:
        r"""
        Documentation here
        """
        return dash.dcc.Dropdown(
            options = [],
            multi=True,
            id="filter_tags_dropdown",
            persistence=True
        )

    @classmethod
    def last_values(cls)->dash.dcc.Dropdown:
        r"""
        Documentation here
        """
        return dash.dcc.Dropdown(
            options=[
                {'label': 'last 10 seconds', 'value': 10},
                {'label': 'last 30 seconds', 'value': 30},
                {'label': 'last minute', 'value': 60},
                {'label': 'last 2 min.', 'value': 2 * 60},
                {'label': 'last 5 min.', 'value': 5 * 60},
                {'label': 'last 10 min.', 'value': 10 * 60}
            ],
            value=10,
            clearable=False,
            id="filter_last_values_dropdown"
        )

    @classmethod
    def current_value_table(cls)->dash.dash_table.DataTable:
        r"""
        Documentation here
        """
        return dash.dash_table.DataTable(
            data=[],
            columns=[ 
                {'name': 'id', 'id': 'id', 'editable': False},
                {'name': 'display_name', 'id': 'display_name', 'editable': False}, 
                {'name': 'gaussian_filter', 'id': 'gaussian_filter', 'type': 'boolean', 'editable': True},
                {'name': 'threshold', 'id': 'threshold', 'type': 'numeric', 'editable': True}, 
                {'name': 'R-value [%]', 'id': 'R-value', 'type': 'numeric', 'editable': True},
            ],
            id="filter_cvt_datatable",
            selected_columns=[],
            page_action="native",
            page_current= 0,
            page_size= 10,
            persistence=True,
            persisted_props=['data']
        )

    @classmethod
    def plot(cls)->dash.dcc.Graph:
        r"""
        Documentation here
        """
        return dash.dcc.Graph(
            figure=fig,
            id="filter_trends_figure")