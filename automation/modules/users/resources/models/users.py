from flask_restx import reqparse

login_parser = reqparse.RequestParser(bundle_errors=True)
login_parser.add_argument("username", type=str, required=False, help='Username')
login_parser.add_argument("email", type=str, required=False, help='User email')
login_parser.add_argument("password", type=str, required=True, help='User password')

signup_parser = reqparse.RequestParser(bundle_errors=True)
signup_parser.add_argument("username", type=str, required=True, help='Username')
signup_parser.add_argument("email", type=str, required=True, help="Email address")
signup_parser.add_argument("password", type=str, required=True, help="Password")
signup_parser.add_argument("name", type=str, required=False, help="User's name")
signup_parser.add_argument("lastname", type=str, required=False, help="User's lastname")

change_password_parser = reqparse.RequestParser(bundle_errors=True)
change_password_parser.add_argument("target_username", type=str, required=True, help='Username whose password will be changed')
change_password_parser.add_argument("new_password", type=str, required=True, help='New password')
change_password_parser.add_argument("current_password", type=str, required=False, help='Current password (required when changing own password)')

reset_password_parser = reqparse.RequestParser(bundle_errors=True)
reset_password_parser.add_argument("target_username", type=str, required=True, help='Username whose password will be reset')
reset_password_parser.add_argument("new_password", type=str, required=True, help='New password')

update_role_parser = reqparse.RequestParser(bundle_errors=True)
update_role_parser.add_argument("target_username", type=str, required=True, help='Username whose role will be updated')
update_role_parser.add_argument("new_role_name", type=str, required=True, help='New role name to assign')

create_tpt_parser = reqparse.RequestParser(bundle_errors=True)
create_tpt_parser.add_argument("role_name", type=str, required=True, help='Role name to embed in the JWT token')