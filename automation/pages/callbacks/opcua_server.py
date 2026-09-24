import dash
from ...pages.components.opcua import OPCUAComponents
from ...opcua.subscription import SubHandler
from ...models import StringType
from ...utils import find_differences_between_lists_opcua_server


subscription_handler = SubHandler()
opcua_components = OPCUAComponents()


def init_callback(app:dash.Dash):

    def create_opcua_server_table(opcua_server_machine):

        listed = getattr(opcua_server_machine, "list_attrs", None)
        if not callable(listed):
            return []
        rows = []
        for row in listed() or []:
            item = dict(row)
            item["access_level"] = item.get("access_level_label") or item.get("access_level")
            rows.append(item)
        return rows

    @app.callback(
        dash.Output("opcua_server_datatable", "data", allow_duplicate=True),
        dash.Input('opcua_server', 'pathname'),
        prevent_initial_call=True
        )
    def display_page(pathname):
        r"""
        Documentation here
        """
        attrs = list()

        if pathname=="/opcua-server":
            opcua_server_machine = app.automation.get_machine(name=StringType("OPCUAServer"))
            attrs = create_opcua_server_table(opcua_server_machine=opcua_server_machine)

        return attrs
    
    @app.callback(
        dash.Input('opcua_server_datatable', 'data_timestamp'),
        dash.State('opcua_server_datatable', 'data_previous'),
        dash.State('opcua_server_datatable', 'data'),
        )
    def update_read_only(timestamp, previous, current):
        message = None
        attr_not_clearable = ("name", "namespace")
        if timestamp:

            if previous and current: # UPDATE TAG DEFINITION
                
                to_updates = find_differences_between_lists_opcua_server(previous, current)
                node_to_update = to_updates[0]
                node_name = node_to_update.pop("name")
                node_to_update.pop("namespace")
                for attr in attr_not_clearable:
                    if attr in node_to_update:
                        if not node_to_update[attr]:
                            message = f"You can not empty {attr} attribute"
                
                if message:
                    dash.set_props("modal-update-opcua-server-body", {"children": message})
                    dash.set_props("modal-update-opcua-server-centered", {'is_open': True})
                    return
                message = f"Do you want to update node {node_name} Access Type to {node_to_update['access_level']}?"
                # OPEN MODAL TO CONFIRM CHANGES
                dash.set_props("modal-update-opcua-server-body", {"children": message})
                dash.set_props("modal-update-opcua-server-centered", {'is_open': True})

    @app.callback(
        [
            dash.Output("modal-update-opcua-server-centered", "is_open"), 
            dash.Output('opcua_server_datatable', 'data'), 
            dash.Output('opcua_server_datatable', 'data_timestamp'),
            dash.Output("update-opcua-server-yes", "n_clicks"),
            dash.Output("update-opcua-server-no", "n_clicks")
        ],
        [dash.Input("update-opcua-server-yes", "n_clicks"), dash.Input("update-opcua-server-no", "n_clicks")],
        [
            dash.State('opcua_server_datatable', 'data_timestamp'),
            dash.State("modal-update-opcua-server-centered", "is_open"),
            dash.State('opcua_server_datatable', 'data_previous'),
            dash.State('opcua_server_datatable', 'data')
        ]
    )
    def toggle_modal_update_read_only(yes_n, no_n, timestamp, is_open, previous, current):
        r"""
        Documentation here
        """
        from ...opcua.subscription import SubHandlerServer

        handler = SubHandlerServer()
        opcua_server_machine = app.automation.get_machine(name=StringType("OPCUAServer"))
        attrs = create_opcua_server_table(opcua_server_machine=opcua_server_machine)

        if yes_n:
            
            if timestamp:
                        
                if previous and current: # UPDATE TAG DEFINITION
                    to_updates = find_differences_between_lists_opcua_server(previous, current)
                    node_to_update = to_updates[0]
                    namespace = node_to_update.pop("namespace")
                    access_level = node_to_update.pop("access_level")
                    app.automation.update_opcua_server_node_access_level(
                        namespace=namespace,
                        access_level=access_level,
                        name=node_to_update.get("name"),
                    )

                    attrs = create_opcua_server_table(opcua_server_machine=opcua_server_machine)

                return not is_open, attrs, None, 0, 0

        elif no_n:
            
            return not is_open, attrs, None, 0, 0

        else:

            return is_open, attrs, None, 0, 0
