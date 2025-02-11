import dash
from ...pages.components.opcua import OPCUAComponents
from ...opcua.subscription import SubHandler
from ...models import StringType
from ...state_machine import Node, ua
from ...utils import find_differences_between_lists_opcua_server


subscription_handler = SubHandler()
opcua_components = OPCUAComponents()


def init_callback(app:dash.Dash):

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
            
            for attr in dir(opcua_server_machine):
                if hasattr(opcua_server_machine, attr):
                    _attr = getattr(opcua_server_machine, attr)
                    if isinstance(_attr, Node):

                        node_class = _attr.get_node_class()
                        if node_class == ua.NodeClass.Variable:
                            
                            browse_name = _attr.get_attribute(ua.AttributeIds.DisplayName)
                            access_level = _attr.get_attribute(ua.AttributeIds.AccessLevel)
                            read_only = not (access_level.Value.Value & ua.AccessLevel.CurrentWrite)
                            attrs.append({
                                "name": browse_name.Value.Value.Text,
                                "namespace": _attr.nodeid.to_string(),
                                "read_only": read_only
                            })
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
                node_namespace = node_to_update.pop("namespace")
                for attr in attr_not_clearable:
                    if attr in node_to_update:
                        if not node_to_update[attr]:
                            message = f"You can not empty {attr} attribute"
                
                if message:
                    dash.set_props("modal-update-opcua-server-body", {"children": message})
                    dash.set_props("modal-update-opcua-server-centered", {'is_open': True})
                    return
                message = f"Do you want to update node {node_name} To read_only {node_to_update['read_only']}?"
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
        attrs = list()
        opcua_server_machine = app.automation.get_machine(name=StringType("OPCUAServer"))
                    
        for attr in dir(opcua_server_machine):
            if hasattr(opcua_server_machine, attr):
                _attr = getattr(opcua_server_machine, attr)
                if isinstance(_attr, Node):

                    node_class = _attr.get_node_class()
                    if node_class == ua.NodeClass.Variable:
                        
                        browse_name = _attr.get_attribute(ua.AttributeIds.DisplayName)
                        access_level = _attr.get_attribute(ua.AttributeIds.AccessLevel)
                        read_only = not (access_level.Value.Value & ua.AccessLevel.CurrentWrite)
                        attrs.append({
                            "name": browse_name.Value.Value.Text,
                            "namespace": _attr.nodeid.to_string(),
                            "read_only": read_only
                        })
        if yes_n:
            
            if timestamp:
                        
                if previous and current: # UPDATE TAG DEFINITION
                    to_updates = find_differences_between_lists_opcua_server(previous, current)
                    node_to_update = to_updates[0]
                    node_name = node_to_update.pop("name")
                    node_namespace = node_to_update.pop("namespace")
                    attrs = list()
                    
                    for attr in dir(opcua_server_machine):
                        if hasattr(opcua_server_machine, attr):
                            _attr = getattr(opcua_server_machine, attr)
                            if isinstance(_attr, Node):

                                node_class = _attr.get_node_class()
                                if node_class == ua.NodeClass.Variable:
                                    
                                    browse_name = _attr.get_attribute(ua.AttributeIds.DisplayName)
                                    access_level = _attr.get_attribute(ua.AttributeIds.AccessLevel)
                                    read_only = not (access_level.Value.Value & ua.AccessLevel.CurrentWrite)
                                    attrs.append({
                                        "name": browse_name.Value.Value.Text,
                                        "namespace": _attr.nodeid.to_string(),
                                        "read_only": read_only
                                    })
                    # tag, message = app.automation.update_tag(id=tag_id, **tag_to_update)
                    
                    # if not tag:
                    #     dash.set_props("modal-body", {"children": message})
                    #     dash.set_props("modal-centered", {'is_open': True})

                return not is_open, attrs, None, 0, 0

        elif no_n:
            
            return not is_open, attrs, None, 0, 0

        else:

            return is_open, attrs, None, 0, 0
