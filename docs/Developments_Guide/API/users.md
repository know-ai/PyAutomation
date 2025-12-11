# Users API

REST API endpoints for user management, authentication, and password operations.

## Authentication

### POST `/api/users/login`

Authenticates a user and returns an API token.

**Request Body:**
```json
{
  "username": "string",
  "email": "string (optional)",
  "password": "string"
}
```

**Response (200):**
```json
{
  "apiKey": "token_string",
  "role": "admin",
  "role_level": 1,
  "datetime": "MM/DD/YYYY, HH:MM:SS",
  "timezone": "America/Lima"
}
```

**Response (403):**
```json
{
  "message": "Invalid credentials"
}
```

### POST `/api/users/logout`

Logs out the current user and invalidates the token.

**Headers:**
- `X-API-KEY`: Authentication token

**Response (200):**
```json
{
  "message": "Logout successfull"
}
```

## User Management

### GET `/api/users/`

Retrieves a list of all registered users.

**Headers:**
- `X-API-KEY`: Authentication token

**Response (200):**
```json
[
  {
    "identifier": "abc123",
    "username": "john_doe",
    "role": {
      "name": "admin",
      "level": 1
    },
    "email": "john@example.com",
    "name": "John",
    "lastname": "Doe"
  }
]
```

### GET `/api/users/<username>`

Retrieves information about a specific user.

**Headers:**
- `X-API-KEY`: Authentication token

**Response (200):**
```json
{
  "identifier": "abc123",
  "username": "john_doe",
  "role": {
    "name": "admin",
    "level": 1
  },
  "email": "john@example.com",
  "name": "John",
  "lastname": "Doe"
}
```

### POST `/api/users/signup`

Registers a new user in the system.

**Request Body:**
```json
{
  "username": "string",
  "role_name": "string",
  "email": "string",
  "password": "string",
  "name": "string (optional)",
  "lastname": "string (optional)"
}
```

**Response (200):**
```json
{
  "identifier": "abc123",
  "username": "new_user",
  "role": {
    "name": "operator",
    "level": 10
  },
  "email": "newuser@example.com"
}
```

## Password Management

### POST `/api/users/change_password`

Changes a user's password with role-based authorization. Requires current password when changing own password.

**Headers:**
- `X-API-KEY`: Authentication token

**Request Body:**
```json
{
  "target_username": "string",
  "new_password": "string",
  "current_password": "string (optional, required when changing own password)"
}
```

**Authorization Rules:**
- **Sudo users**: Can only change passwords of users with role "admin" (cannot change their own password)
- **Admin users**: Can change passwords of users with `role_level >= admin`
- **Other roles**: Can only change their own password
- **Own password change**: Requires `current_password` validation

**Response (200):**
```json
{
  "message": "Password changed successfully"
}
```

**Response (400):**
```json
{
  "message": "Error message describing the issue"
}
```

**Response (401):**
```json
{
  "message": "Token is required"
}
```

**Example - User changing own password:**
```bash
curl -X POST 'http://localhost:8050/api/users/change_password' \
  -H 'X-API-KEY: your_token_here' \
  -H 'Content-Type: application/json' \
  -d '{
    "target_username": "john_doe",
    "new_password": "newSecurePassword123",
    "current_password": "oldPassword"
  }'
```

**Example - Admin changing another user's password:**
```bash
curl -X POST 'http://localhost:8050/api/users/change_password' \
  -H 'X-API-KEY: admin_token_here' \
  -H 'Content-Type: application/json' \
  -d '{
    "target_username": "operator1",
    "new_password": "newSecurePassword123"
  }'
```

### POST `/api/users/reset_password`

Resets a user's password (for forgotten password scenario) with role-based authorization. No current password validation required.

**Headers:**
- `X-API-KEY`: Authentication token

**Request Body:**
```json
{
  "target_username": "string",
  "new_password": "string"
}
```

**Authorization Rules:**
- **Sudo users**: Can only reset passwords of users with role "admin" (cannot reset their own password)
- **Admin users**: Can reset passwords of users with `role_level >= admin`
- **Other roles**: Can only reset their own password
- **No current password validation**: Suitable for forgotten password scenarios

**Response (200):**
```json
{
  "message": "Password reset successfully"
}
```

**Response (400):**
```json
{
  "message": "Error message describing the issue"
}
```

**Response (401):**
```json
{
  "message": "Token is required"
}
```

**Example - User resetting own password:**
```bash
curl -X POST 'http://localhost:8050/api/users/reset_password' \
  -H 'X-API-KEY: your_token_here' \
  -H 'Content-Type: application/json' \
  -d '{
    "target_username": "john_doe",
    "new_password": "newSecurePassword123"
  }'
```

**Example - Admin resetting another user's password:**
```bash
curl -X POST 'http://localhost:8050/api/users/reset_password' \
  -H 'X-API-KEY: admin_token_here' \
  -H 'Content-Type: application/json' \
  -d '{
    "target_username": "operator1",
    "new_password": "newSecurePassword123"
  }'
```

## Third Party Tokens (TPT)

### POST `/api/users/create_tpt`

Creates a JWT Third Party Token (TPT) for third-party integration. **Only sudo users can access this endpoint.**

**Headers:**
- `X-API-KEY`: Authentication token (must be from a sudo user)

**Request Body:**
```json
{
  "role_name": "string"
}
```

**Response (200):**
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "role": "admin",
  "created_on": "2024-01-15 10:30:45",
  "message": "Third Party Token created successfully"
}
```

**Response (403):**
```json
{
  "message": "Access denied. Required roles: ['sudo']"
}
```

**Response (401):**
```json
{
  "message": "Token is required"
}
```

**Example:**
```bash
curl -X POST 'http://localhost:8050/api/users/create_tpt' \
  -H 'X-API-KEY: sudo_user_token' \
  -H 'Content-Type: application/json' \
  -d '{
    "role_name": "admin"
  }'
```

**Use Cases:**
- Third-party system integration
- Automated API access without user login
- Service-to-service authentication
- Long-lived tokens for external applications

**Security Notes:**
- Tokens are signed using `AUTOMATION_APP_SECRET_KEY`
- Only sudo users can create TPT tokens
- Tokens contain the role name in the payload
- Tokens can be verified using `Api.verify_tpt()` method

## Core Methods

### `change_password(target_username, new_password, current_password=None)`

Internal method for changing a user's password without authorization restrictions.

**Parameters:**
- `target_username` (str): Username whose password will be changed
- `new_password` (str): New password to set
- `current_password` (str, optional): Current password for validation

**Returns:**
- `tuple[str|None, str]`: Success message or None, and status message

**Usage:**
```python
from automation import PyAutomation

app = PyAutomation()
message, status = app.change_password(
    target_username="john_doe",
    new_password="newSecurePassword123",
    current_password="oldPassword"  # Optional, for validation
)
```

### `reset_password(target_username, new_password)`

Internal method for resetting a user's password without authorization restrictions. No current password validation.

**Parameters:**
- `target_username` (str): Username whose password will be reset
- `new_password` (str): New password to set

**Returns:**
- `tuple[str|None, str]`: Success message or None, and status message

**Usage:**
```python
from automation import PyAutomation

app = PyAutomation()
message, status = app.reset_password(
    target_username="john_doe",
    new_password="newSecurePassword123"
)
```

