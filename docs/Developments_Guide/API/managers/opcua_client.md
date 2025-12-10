# OPC UA Client Manager API

The `OPCUAClientManager` handles multiple OPC UA client connections. It abstracts connection logic, node browsing, and reading/writing values, providing a unified interface for the rest of the application.

::: automation.managers.opcua_client.OPCUAClientManager
    :docstring:
    :members: discovery
    :members: add
    :members: remove
    :members: connect
    :members: disconnect
    :members: get
    :members: get_opcua_tree
    :members: get_node_values
    :members: get_client_by_address
    :members: get_node_value_by_opcua_address
    :members: get_node_attributes
    :members: serialize

