import dash
from ...pages.components.opcua import OPCUAComponents
from ...opcua.subscription import SubHandler
from ...models import StringType
from ...state_machine import Node, ua


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
        print(attrs)
        return attrs
