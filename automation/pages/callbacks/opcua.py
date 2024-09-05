import dash
from automation.utils import get_nodes_info, get_data_to_update_into_opcua_table
from automation.pages.components.opcua import OPCUAComponents
from automation.opcua.subscription import SubHandler


subscription_handler = SubHandler()
opcua_components = OPCUAComponents()


def init_callback(app:dash.Dash):
    
    @app.callback(
        dash.Output("data_access_view_table", "children", allow_duplicate=True),
        dash.Input('timestamp-interval', 'n_intervals'),
        dash.State({'type': 'file-checklist', 'index': dash.dependencies.ALL}, 'value'),
        prevent_initial_call=False
    )
    def update_data_access_table( n_intervals, selected_files):
        
        to_get_node_values = get_nodes_info(selected_files=selected_files)
        data = get_data_to_update_into_opcua_table(app=app, to_get_node_values=to_get_node_values)
        
        return opcua_components.data_access_view_table(data=data)

    @app.callback(
        dash.Output("data_access_view_table", "children"),
        dash.Input({'type': 'file-checklist', 'index': dash.dependencies.ALL}, 'value')
    )
    def display_selected_file(selected_files):

        subscription_handler.unsubscribe_all()
        to_get_node_values = get_nodes_info(selected_files=selected_files)

        data = list()
        subscriptions = dict()
        for client_name, namespaces in to_get_node_values.items():
            
            client = app.automation.get_opcua_client(client_name=client_name)
            subscriptions[client_name] = client.create_subscription(1000, subscription_handler)
            infos = app.automation.get_node_attributes(client_name=client_name, namespaces=namespaces)
            
            for info in infos:
                _info = info[0]
                namespace = _info["Namespace"]
                data.append(
                    {
                        "server": client_name,
                        "namespace": namespace,
                        "data_type": _info["DataType"],
                        "display_name": _info["DisplayName"],
                        "value": _info["Value"],
                        "source_timestamp": _info["DataValue"].SourceTimestamp,
                        "status_code": _info["DataValue"].StatusCode.name
                    }
                )
                
                node_id = client.get_node_id_by_namespace(namespace)
                subscription = subscriptions[client_name]
                subscription_handler.subscribe(subscription=subscription, client_name=client_name, node_id=node_id, server=client_name)

        return opcua_components.data_access_view_table(data=data)

    @app.callback(
        dash.Output("add_server_modal", "is_open"),
        dash.Input("add_server_button", "n_clicks"),
        [dash.State("add_server_modal", "is_open")],
    )
    def add_server_button(n, is_open):
        r"""
        Documentation here
        """
        if n:

            return not is_open
        
        return is_open
    
    @app.callback(
        dash.Output("add_server_modal", "is_open", allow_duplicate=True),
        dash.Output("server_tree", "children"),
        dash.Input("add_server_ok_button_modal", "n_clicks"),
        dash.State("opcua_client_name_input", "value"),
        dash.State("opcua_client_host_input", "value"),
        dash.State("opcua_client_port_input", "value")
    )
    def ok_add_server_button(n, client_name:str, host:str="127.0.0.1", port:int=4840):
        r"""
        Documentation here
        """
        app.automation.add_opcua_client(client_name=client_name, host=host, port=port)
        data = OPCUAComponents.get_opcua_tree(app)
        subscription_handler.unsubscribe_all()

        return False, data
    
    @app.callback(
        dash.Output("add_server_modal", "is_open", allow_duplicate=True),
        dash.Input("add_server_cancel_button_modal", "n_clicks"),
    )
    def cancel_add_server_button(n):
        r"""
        Documentation here
        """
        return False
    
    @app.callback(
        dash.Output("server_tree", "children", allow_duplicate=True),
        dash.Input('communications_page', 'pathname'),
        prevent_initial_call=True
        )
    def display_page(pathname):
        r"""
        Documentation here
        """
        if pathname=="/":

            data = OPCUAComponents.get_opcua_tree(app)
            subscription_handler.unsubscribe_all()
            
            return data