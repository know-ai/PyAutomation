import dash, csv, io
from ...utils import get_nodes_info, get_data_to_update_into_opcua_table
from ...pages.components.opcua import OPCUAComponents
from ...opcua.subscription import SubHandler


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
            if client:
                subscriptions[client_name] = client.create_subscription(1000, subscription_handler)
                infos = app.automation.get_node_attributes(client_name=client_name, namespaces=namespaces)
                if infos:
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
                        subscription_handler.subscribe(subscription=subscription, client_name=client_name, node_id=node_id)

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
        dash.Output("remove_server_modal", "is_open"),
        dash.Input("remove_server_button", "n_clicks"),
        [dash.State("remove_server_modal", "is_open")],
    )
    def remove_server_button(n, is_open):
        r"""
        Documentation here
        """
        if n:
            clients = list()
            for client_name in app.automation.get_opcua_clients().keys():

                clients.append(
                    {"label": client_name, "value": client_name}
                )

            dash.set_props("opcua_client_names_options", {"options": clients})
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
        resp, _ = app.automation.add_opcua_client(client_name=client_name, host=host, port=port)
        if resp:

            data = OPCUAComponents.get_opcua_tree(app)
            subscription_handler.unsubscribe_all()        

            return False, data
        
        message = f"Connection refused on opc.tcp://{host}:{port}"
        dash.set_props("modal-error-opcua-connection-body", {"children": message})
        dash.set_props("modal-error-opcua-connection", {'is_open': True})

        return False, {}
    
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
        dash.Output("remove_server_modal", "is_open", allow_duplicate=True),
        dash.Input("remove_server_ok_button_modal", "n_clicks"),
        dash.State("opcua_client_names_options", "value")
    )
    def ok_remove_server_button(n, client_name:str):
        r"""
        Documentation here
        """
        if client_name:

            app.automation.remove_opcua_client(client_name=client_name)

        data = OPCUAComponents.get_opcua_tree(app)
        dash.set_props("server_tree", {"children": data})
        return False
    
    @app.callback(
        dash.Output("remove_server_modal", "is_open", allow_duplicate=True),
        dash.Input("remove_server_cancel_button_modal", "n_clicks"),
    )
    def cancel_remove_server_button(n):
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
        
    @app.callback(
        dash.Output("modal-success-opcua-connection", "is_open"),
        dash.Input("close-success-opcua-connection", "n_clicks"),
        [dash.State("modal-success-opcua-connection", "is_open")],
    )
    def close_success_button(n, is_open):
        r"""
        Documentation here
        """
        if n:

            return not is_open
        
        return is_open
    
    @app.callback(
        dash.Output("modal-error-opcua-connection", "is_open"),
        dash.Input("close-error-opcua-connection", "n_clicks"),
        [dash.State("modal-error-opcua-connection", "is_open")],
    )
    def close_error_opcua_connection_button(n, is_open):
        r"""
        Documentation here
        """
        if n:

            return not is_open
        
        return is_open
    
    @app.callback(
        dash.Output("download_node_info_modal", "is_open"),
        dash.Input("download_node_info_button", "n_clicks"),
        [dash.State("download_node_info_modal", "is_open")],
    )
    def download_node_info_button(n, is_open):
        r"""
        Documentation here
        """
        if n:
            clients = list()
            for client_name in app.automation.get_opcua_clients().keys():

                clients.append(
                    {"label": client_name, "value": client_name}
                )

            dash.set_props("download_opcua_client_names_options", {"options": clients})
            return not is_open
        
        return is_open
    
    @app.callback(
        dash.Output("download_node_info_modal", "is_open", allow_duplicate=True),
        dash.Output("download", "data"),
        dash.Input("download_node_info_ok_button_modal", "n_clicks"),
        dash.State("download_opcua_client_names_options", "value")
    )
    def ok_download_node_info_button(n, client_name:str):
        r"""
        Documentation here
        """
        if client_name:

            opcua_tree = app.automation.get_opcua_tree(client_name=client_name)
            opcua_tree = opcua_tree[0]['Objects']
            flat = list()
            for tree in opcua_tree:
                
                flat.extend(OPCUAComponents.flatten_dict(tree))
            output = io.StringIO() 
            writer = csv.DictWriter(output, fieldnames=["name", "namespace", "NodeClass"]) 
            writer.writeheader() 
            writer.writerows(flat)
            
        return False, dict(content=output.getvalue(), filename=f"opcua_server_node_{client_name}.csv")
    
    @app.callback(
        dash.Output("download_node_info_modal", "is_open", allow_duplicate=True),
        dash.Input("download_node_info_cancel_button_modal", "n_clicks"),
    )
    def cancel_remove_server_button(n):
        r"""
        Documentation here
        """
        return False