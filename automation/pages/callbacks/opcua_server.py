import dash
from ...pages.components.opcua import OPCUAComponents
from ...opcua.subscription import SubHandler
from ...models import StringType
from ...state_machine import Node, ua
from ...utils import find_differences_between_lists_opcua_server


subscription_handler = SubHandler()
opcua_components = OPCUAComponents()


def init_callback(app:dash.Dash):

    def create_opcua_server_table(opcua_server_machine):

        attrs = list()        
        for attr in dir(opcua_server_machine):
            if hasattr(opcua_server_machine, attr):
                node = getattr(opcua_server_machine, attr)
                if isinstance(node, Node):

                    node_class = node.get_node_class()
                    if node_class == ua.NodeClass.Variable:
                        
                        browse_name = node.get_attribute(ua.AttributeIds.DisplayName)
                        access_level = node.get_access_level()
                        # Verificar los niveles de acceso
                        write_only = ua.AccessLevel.CurrentWrite in access_level and ua.AccessLevel.CurrentRead not in access_level
                        read_write = ua.AccessLevel.CurrentRead in access_level and ua.AccessLevel.CurrentWrite in access_level
                        access_type = "Read"
                        if write_only:

                            access_type = "Write"
                        
                        elif read_write:

                            access_type = "ReadWrite"

                        attrs.append({
                            "name": browse_name.Value.Value.Text,
                            "namespace": node.nodeid.to_string(),
                            "access_type": access_type
                        })
        return attrs

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
                message = f"Do you want to update node {node_name} Access Type to {node_to_update['access_type']}?"
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
                    access_type = node_to_update.pop("access_type")
                    # Code for update read_only attribute
                    opcua_server_machine = app.automation.get_machine(name=StringType("OPCUAServer"))
                    opcua_server_attrs = dir(opcua_server_machine)
                    attr = False
                    for i, item in enumerate(opcua_server_attrs):
                    
                        if hasattr(opcua_server_machine, item):
                            node = getattr(opcua_server_machine, item)
                            if isinstance(node, Node):

                                node_class = node.get_node_class()

                                if node_class == ua.NodeClass.Variable:
                                    
                                    if node.nodeid.to_string()==namespace:
                                        
                                        attr = opcua_server_attrs[i]
                                        break                                        
                    
                    if attr:
                        node = getattr(opcua_server_machine, attr)
                        opcua_server_obj = app.automation.get_opcua_server_record_by_namespace(namespace=namespace)
                        if opcua_server_obj:
                            app.automation.update_opcua_server_access_type(namespace=namespace, access_type=access_type)
                        else:
                            app.automation.create_opcua_server_record(name=node_to_update["name"], namespace=namespace, access_type=access_type)
                        access_type = access_type.lower()
                        # Limpiar todos los bits de acceso primero
                        node.unset_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentRead)
                        node.unset_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentWrite)
                        node.unset_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentRead)
                        node.unset_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentWrite)

                        subscriptions = handler.subscriptions
                        # Unsubscribe

                        if namespace in subscriptions:

                            _sub = subscriptions.pop(namespace)
                            _sub.delete()
                        
                        if access_type == "write":
                            # Solo escritura: deshabilitamos la lectura y habilitamos la escritura
                            node.set_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentWrite)
                            node.set_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentWrite)
                            sub = opcua_server_machine.server.create_subscription(100, handler)
                            sub.subscribe_data_change(node)
                            handler.subscriptions[namespace] = sub
                        elif access_type == "read":
                            # Solo lectura: habilitamos la lectura y deshabilitamos la escritura
                            node.set_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentRead)
                            node.set_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentRead)
                        elif access_type == "readwrite":
                            # Lectura y escritura: habilitamos ambos
                            node.set_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentRead)
                            node.set_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentWrite)
                            node.set_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentRead)
                            node.set_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentWrite)
                            sub = opcua_server_machine.server.create_subscription(100, handler)
                            sub.subscribe_data_change(node)
                            handler.subscriptions[namespace] = sub

                    attrs = create_opcua_server_table(opcua_server_machine=opcua_server_machine)


                return not is_open, attrs, None, 0, 0

        elif no_n:
            
            return not is_open, attrs, None, 0, 0

        else:

            return is_open, attrs, None, 0, 0
