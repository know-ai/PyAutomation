# Database Manager API

The `DBManager` orchestrates all database interactions. It serves as a facade for various specialized logger engines (Alarms, Events, Tags) and handles the database connection lifecycle.

::: automation.managers.db.DBManager
    :docstring:
    :members: get_queue
    :members: set_db
    :members: get_db
    :members: set_dropped
    :members: get_dropped
    :members: register_table
    :members: get_db_table
    :members: create_tables
    :members: drop_tables
    :members: clear_default_tables
    :members: get_tags
    :members: get_alarms
    :members: set_tag
    :members: init_database
    :members: stop_database
    :members: get_opcua_clients
    :members: set_role
    :members: set_user
    :members: login
    :members: summary
    :members: attach
