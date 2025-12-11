# API Authorization Decorators

PyAutomation provides decorators for implementing role-based access control (RBAC) in REST API endpoints.

## Overview

Authorization decorators allow you to restrict access to endpoints based on:
- **Role names**: Specific roles that can access the endpoint
- **Role levels**: Maximum role level allowed (lower number = higher privilege)

## Decorators

### `@Api.token_required(auth=True)`

Base decorator that requires authentication via token. Must be used before other authorization decorators.

**Usage:**
```python
@Api.token_required(auth=True)
def get(self):
    # Endpoint requires authentication
    pass
```

### `@Api.auth_roles(role_names: list[str])`

Restricts access to endpoints based on a list of role names. Only users with one of the specified roles can access the endpoint.

**Parameters:**
- `role_names` (list[str]): List of role names allowed to access the endpoint

**Usage:**
```python
@Api.token_required(auth=True)
@Api.auth_roles(['admin', 'supervisor'])
def post(self):
    # Only users with role 'admin' or 'supervisor' can access
    pass
```

**Example:**
```python
@ns.route('/admin_only')
class AdminResource(Resource):
    
    @Api.token_required(auth=True)
    @Api.auth_roles(['admin'])
    def post(self):
        """Only admin users can access this endpoint"""
        return {'message': 'Admin access granted'}, 200
```

**Response (403) if unauthorized:**
```json
{
  "message": "Access denied. Required roles: ['admin', 'supervisor']"
}
```

### `@Api.auth_role_level(max_level: int)`

Restricts access to endpoints based on role level. Users with `role_level <= max_level` are allowed access.

**Parameters:**
- `max_level` (int): Maximum role level allowed (inclusive). Lower numbers = higher privilege.

**Role Levels:**
- `0`: sudo (highest privilege)
- `1`: admin
- `2`: supervisor
- `10`: operator
- `100`: auditor
- `256`: guest (lowest privilege)

**Usage:**
```python
@Api.token_required(auth=True)
@Api.auth_role_level(1)  # Only admin (level 1) and sudo (level 0) can access
def post(self):
    # Only users with role_level <= 1 can access
    pass
```

**Example:**
```python
@ns.route('/admin_and_above')
class AdminLevelResource(Resource):
    
    @Api.token_required(auth=True)
    @Api.auth_role_level(1)  # Admin and sudo
    def post(self):
        """Only admin and sudo users can access"""
        return {'message': 'Access granted'}, 200
```

**Response (403) if unauthorized:**
```json
{
  "message": "Access denied. Required role level: <= 1"
}
```

## Combining Decorators

Decorators can be combined. The order matters:

1. `@Api.token_required(auth=True)` - Must be first
2. `@Api.auth_roles()` or `@Api.auth_role_level()` - Authorization decorator

**Example with both:**
```python
@Api.token_required(auth=True)
@Api.auth_roles(['admin'])
@Api.auth_role_level(1)  # This is redundant if auth_roles is already used
def post(self):
    pass
```

**Note:** Using both `auth_roles` and `auth_role_level` together is usually redundant. Choose the one that best fits your needs.

## Complete Example

```python
from flask_restx import Namespace, Resource
from ....extensions.api import api
from ....extensions import _api as Api

ns = Namespace('Admin', description='Administrative operations')

@ns.route('/create_user')
class CreateUserResource(Resource):
    
    @api.doc(security='apikey', description="Creates a new user. Admin access required.")
    @api.response(200, "Success")
    @api.response(403, "Forbidden")
    @Api.token_required(auth=True)
    @Api.auth_role_level(1)  # Only admin and sudo
    def post(self):
        """
        Create user.
        
        Only users with role_level <= 1 (admin or sudo) can access this endpoint.
        """
        # Your implementation here
        return {'message': 'User created'}, 200

@ns.route('/sudo_only')
class SudoResource(Resource):
    
    @api.doc(security='apikey', description="Sudo-only operation.")
    @api.response(200, "Success")
    @api.response(403, "Forbidden")
    @Api.token_required(auth=True)
    @Api.auth_roles(['sudo'])  # Only sudo role
    def post(self):
        """
        Sudo operation.
        
        Only users with the 'sudo' role can access this endpoint.
        """
        # Your implementation here
        return {'message': 'Sudo operation completed'}, 200
```

## Error Responses

### 401 Unauthorized
Returned when:
- Token is missing
- Token is invalid
- User not found

```json
{
  "message": "Token is required"
}
```

### 403 Forbidden
Returned when:
- User's role is not in the allowed list (`auth_roles`)
- User's role level is higher than allowed (`auth_role_level`)

```json
{
  "message": "Access denied. Required roles: ['admin']"
}
```

or

```json
{
  "message": "Access denied. Required role level: <= 1"
}
```

## Best Practices

1. **Always use `token_required` first**: Authentication must be checked before authorization
2. **Choose the right decorator**: Use `auth_roles` for specific roles, `auth_role_level` for privilege levels
3. **Document restrictions**: Clearly document in endpoint docstrings which roles can access
4. **Test authorization**: Verify that unauthorized users receive 403 responses
5. **Minimal privilege**: Grant the minimum required access level
6. **Error messages**: Provide clear error messages for debugging

## Implementation Details

Both decorators:
- Extract the token from `X-API-KEY` or `Authorization` headers
- Check the user in CVT (Current Value Table) first
- Fall back to database lookup if user not in CVT
- Compare role names/levels case-insensitively
- Return appropriate HTTP status codes (401, 403, 500)

