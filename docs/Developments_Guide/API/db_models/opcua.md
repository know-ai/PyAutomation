# OPC UA Models

Models for configuring OPC UA Clients and Server nodes.

::: automation.dbmodels.opcua.OPCUA
:docstring:
:members: create
:members: get_by_client_name
:members: client_name_exist
:members: serialize

::: automation.dbmodels.opcua_server.OPCUAServer
    :docstring:
    :members: create
    :members: read_by_name
    :members: read_by_namespace
    :members: namespace_exist
    :members: update_access_type
    :members: name_exist
    :members: serialize

::: automation.dbmodels.opcua_server.AccessType
    :docstring:
    :members: create
    :members: read_by_name
    :members: name_exist
    :members: serialize
