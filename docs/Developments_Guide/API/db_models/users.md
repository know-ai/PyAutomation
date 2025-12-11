# Users Models

Models for managing user authentication, authorization, and roles.

::: automation.dbmodels.users.Users
    :docstring:
    :members: create
    :members: login
    :members: logout
    :members: update_password
    :members: read_by_username
    :members: read_by_name
    :members: name_exist
    :members: username_exist
    :members: email_exist
    :members: identifier_exist
    :members: encode
    :members: decode_password
    :members: decode_token
    :members: fill_cvt_users
    :members: serialize

::: automation.dbmodels.users.Roles
    :docstring:
    :members: create
    :members: read_by_name
    :members: read_by_identifier
    :members: name_exist
    :members: identifier_exist
    :members: read_names
    :members: fill_cvt_roles
    :members: serialize
