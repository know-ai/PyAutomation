from flask_restx import reqparse

login_parser = reqparse.RequestParser(bundle_errors=True)
login_parser.add_argument("username", type=str, required=False, help='Username')
login_parser.add_argument("email", type=str, required=False, help='User email')
login_parser.add_argument("password", type=str, required=True, help='User passqord')

signup_parser = reqparse.RequestParser(bundle_errors=True)
signup_parser.add_argument("username", type=str, required=True, help='Username')
signup_parser.add_argument("role_name", type=str, required=True, help='Role Name')
signup_parser.add_argument("email", type=str, required=True, help="Email address")
signup_parser.add_argument("password", type=str, required=True, help="Password")
signup_parser.add_argument("name", type=str, required=False, help="User's name")
signup_parser.add_argument("lastname", type=str, required=False, help="User's lastname")