import dash
import dash_bootstrap_components as dbc
from automation.pages.components import Components
from automation.pages.components.gaussian_filter import FilterComponents

dash.register_page(__name__)

layout = dbc.Container(
    [
        dbc.Breadcrumb(
            items=[
                {"label": "Home", "href": "/"},
                {"label": "Tags", "href": "/tags"},
                {"label": "Filter", "active": True},
            ],
        ),
        dash.dcc.Location(id='filter_page', refresh=False),
        dbc.Row(
            [
                dbc.Col(FilterComponents.tags(), width=6, className="col-sm-6 col-md-10"),
                dbc.Col(FilterComponents.last_values(), width=6, className="col-sm-6 col-md-2 ps-0"),
            ],
            className="mb-3"
        ),
        dbc.Row(
            [
                dbc.Col(FilterComponents.current_value_table(), width=12, className="col-sm-12 col-md-12 mb-2"),
                dbc.Col(FilterComponents.plot(), width=12, className="col-sm-12 col-md-12"),
            ],
            className="mb-3"
        ),
        Components.modal_error(
            title="Error",
            modal_id="modal-error-filter-tags",
            button_close_id="close-modal-error-filter",
            body_id="modal-error-filter-tags-body"
        ),
        Components.modal_error(
            title="Success",
            modal_id="modal-success-filter-tags",
            button_close_id="close-modal-success-filter-tags",
            body_id="modal-success--filter-tags-body"
        ),
        Components.modal_confirm(
            title="Confirmation",
            modal_id="modal-update-filter-tags",
            body_id="modal-update-filter-tags-body",
            yes_button_id="update-filter-tags-yes",
            no_button_id="update-filter-tags-no"
        ),
    ],
    fluid=False,
    className="my-3"
)
    