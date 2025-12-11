# User Management

The **User Management** module provides comprehensive functionality for managing user accounts, authentication, and password operations in PyAutomation.

## Overview

PyAutomation implements a role-based access control (RBAC) system that allows you to:
- Create and manage user accounts
- Assign roles with different permission levels
- Authenticate users and manage sessions
- Change and reset user passwords with proper authorization

## User Roles

PyAutomation includes the following default roles (ordered by permission level, lower number = higher privilege):

- **sudo** (level 0): Highest privilege, system administrator
- **admin** (level 1): Administrative access
- **supervisor** (level 2): Supervisory access
- **operator** (level 10): Operator access
- **auditor** (level 100): Read-only access for auditing
- **guest** (level 256): Limited guest access

## Authentication

### Login

To authenticate and obtain an API token:

1. Send a POST request to `/api/users/login` with your credentials:
   ```json
   {
     "username": "your_username",
     "password": "your_password"
   }
   ```

2. The server responds with an API token:
   ```json
   {
     "apiKey": "your_token_here",
     "role": "admin",
     "role_level": 1,
     "datetime": "MM/DD/YYYY, HH:MM:SS",
     "timezone": "America/Lima"
   }
   ```

3. Use this token in subsequent requests by including it in the `X-API-KEY` header.

### Logout

To invalidate your session token, send a POST request to `/api/users/logout` with your token in the `X-API-KEY` header.

## Password Management

PyAutomation provides two methods for password management, each with specific use cases and authorization rules.

### Changing Password

Use the **change password** functionality when you know your current password and want to update it.

**Endpoint:** `POST /api/users/change_password`

**When to use:**
- You remember your current password
- You want to update your password as a security measure
- An administrator wants to change another user's password (with proper authorization)

**Requirements:**
- When changing your own password: `current_password` is required
- When an admin changes another user's password: `current_password` is not required

**Authorization Rules:**
- **Sudo users**: Can only change passwords of users with role "admin" (cannot change their own password)
- **Admin users**: Can change passwords of users with `role_level >= admin`
- **Other roles**: Can only change their own password

**Example Request:**
```json
{
  "target_username": "john_doe",
  "new_password": "newSecurePassword123",
  "current_password": "oldPassword"
}
```

### Resetting Password

Use the **reset password** functionality when a password has been forgotten or needs to be reset without knowing the current password.

**Endpoint:** `POST /api/users/reset_password`

**When to use:**
- You have forgotten your password
- An administrator needs to reset a user's password without knowing the current one
- Password recovery scenarios

**Requirements:**
- No `current_password` is required
- Still requires proper authorization based on user roles

**Authorization Rules:**
- **Sudo users**: Can only reset passwords of users with role "admin" (cannot reset their own password)
- **Admin users**: Can reset passwords of users with `role_level >= admin`
- **Other roles**: Can only reset their own password

**Example Request:**
```json
{
  "target_username": "john_doe",
  "new_password": "newSecurePassword123"
}
```

## Common Scenarios

### Scenario 1: User Changing Own Password

**Situation:** A regular user wants to update their password.

**Steps:**
1. Authenticate to get a token
2. Send POST request to `/api/users/change_password`:
   ```json
   {
     "target_username": "your_username",
     "new_password": "newPassword123",
     "current_password": "oldPassword"
   }
   ```
3. Include your token in the `X-API-KEY` header

**Result:** Password is updated if current password is correct.

### Scenario 2: Admin Resetting Operator Password

**Situation:** An admin needs to reset an operator's forgotten password.

**Steps:**
1. Admin authenticates to get a token
2. Send POST request to `/api/users/reset_password`:
   ```json
   {
     "target_username": "operator1",
     "new_password": "newPassword123"
   }
   ```
3. Include admin token in the `X-API-KEY` header

**Result:** Operator's password is reset (admin has permission because operator role_level >= admin).

### Scenario 3: User Forgot Password

**Situation:** A user has forgotten their password and needs to reset it.

**Steps:**
1. User must still have a valid session token (or request admin assistance)
2. If user has token, send POST request to `/api/users/reset_password`:
   ```json
   {
     "target_username": "your_username",
     "new_password": "newPassword123"
   }
   ```
3. Include token in the `X-API-KEY` header

**Note:** If the user cannot authenticate, they will need to contact an administrator to reset their password.

## Third Party Tokens (TPT)

Third Party Tokens (TPT) are JWT tokens designed for third-party system integration. These tokens allow external applications to authenticate with PyAutomation without requiring user login credentials.

### Creating TPT Tokens

**Who can create TPT tokens:**
- Only users with the **sudo** role can create TPT tokens

**How to create a TPT token:**

1. Authenticate as a sudo user to obtain your API token
2. Send a POST request to `/api/users/create_tpt`:
   ```json
   {
     "role_name": "admin"
   }
   ```
3. Include your sudo user token in the `X-API-KEY` header

**Response:**
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "role": "admin",
  "created_on": "2024-01-15 10:30:45",
  "message": "Third Party Token created successfully"
}
```

### Using TPT Tokens

TPT tokens can be used in the `X-API-KEY` header just like regular user tokens. The token contains:
- **Role**: The role name embedded in the token
- **Created timestamp**: When the token was created

**Example usage:**
```bash
curl -X GET 'http://localhost:8050/api/tags/' \
  -H 'X-API-KEY: tpt_token_here'
```

### Use Cases

- **Third-party integrations**: Allow external systems to access PyAutomation APIs
- **Automated services**: Enable service-to-service communication
- **Long-lived access**: Create tokens that don't expire with user sessions
- **System integration**: Connect PyAutomation with other industrial systems

### Security Considerations

- TPT tokens are signed using `AUTOMATION_APP_SECRET_KEY`
- Only sudo users can create these tokens
- Tokens should be stored securely in third-party systems
- Regularly rotate TPT tokens for enhanced security
- Use the minimum required role level for the token

## Security Best Practices

1. **Use strong passwords**: Choose passwords with a mix of letters, numbers, and special characters
2. **Change passwords regularly**: Update your password periodically as a security measure
3. **Don't share tokens**: Keep your API tokens secure and don't share them with others
4. **Logout when done**: Always logout when finished to invalidate your session token
5. **Role-based access**: Understand your role's permissions and limitations
6. **Secure TPT tokens**: Store third-party tokens securely and rotate them regularly
7. **Minimal privilege**: Create TPT tokens with the minimum required role level

## Error Handling

Common error responses:

**401 Unauthorized:**
```json
{
  "message": "Token is required"
}
```
Solution: Include a valid token in the `X-API-KEY` header.

**400 Bad Request:**
```json
{
  "message": "Current password is required when changing your own password"
}
```
Solution: Provide `current_password` when changing your own password.

**400 Bad Request:**
```json
{
  "message": "You can only change your own password"
}
```
Solution: You don't have permission to change other users' passwords. Contact an administrator.

**400 Bad Request:**
```json
{
  "message": "Sudo users cannot change their own password"
}
```
Solution: Sudo users cannot change their own password. Contact another sudo user or use system recovery methods.

