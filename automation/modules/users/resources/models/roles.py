from flask_restx import reqparse

create_role_parser = reqparse.RequestParser(bundle_errors=True)
create_role_parser.add_argument("name", type=str, required=True, help='Role name')
create_role_parser.add_argument("level", type=int, required=True, help='Role level, 0 maximum level', default=0)