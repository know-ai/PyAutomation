# Database Configuration

<div align="center" style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 15px; padding: 3em 2em; margin: 2em 0; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">

<h2 style="color: #1b5e20; font-size: 2.5em; margin-bottom: 0.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.1); font-weight: 700;">
  💾 Reliable Data Persistence
</h2>

<p style="color: #0d4f1c; font-size: 1.4em; margin-top: 1em; font-weight: 500;">
  The <strong>Database Module</strong> is essential for enabling historical data storage, event logging, and data persistence in PyAutomation. This module allows you to connect to external relational database management systems (RDBMS), providing robust data storage capabilities for tags, alarms, events, and operational logs.
</p>

</div>

## Overview

<div style="background: #f8f9fa; border-left: 5px solid #4caf50; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 500;">
The database configuration interface is located in the top navigation bar of the PyAutomation application, providing quick access to database connection settings from any module. This centralized location allows you to manage your database connection without navigating away from your current work.
</p>

</div>

![Database Configuration in Navigation Bar](../images/DatabaseConfigInNavBar.png)

## Initial Configuration via Environment Variables (.env)

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 2em 0; border: 2px solid #4caf50;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
On the <strong>very first startup</strong> of PyAutomation, before any database configuration has been established through the user interface, you can configure the initial database connection using environment variables. This approach is particularly useful for:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Automated deployments and CI/CD pipelines</li>
<li>Docker container configurations</li>
<li>Infrastructure-as-code scenarios</li>
<li>Initial setup before accessing the HMI interface</li>
</ul>

</div>

### When Bootstrap Configuration Applies

<div style="background: #f8f9fa; border-left: 5px solid #4caf50; padding: 1.5em; margin: 1.5em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
The bootstrap configuration from environment variables <strong>only works</strong> when:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>There is <strong>no existing</strong> <code>db/db_config.json</code> file in the PyAutomation installation directory</li>
<li>The appropriate <code>AUTOMATION_DB_*</code> environment variables are defined</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; font-weight: 400;">
Once <code>db/db_config.json</code> is created (either from environment variables or through the HMI), it becomes the <strong>single source of truth</strong>. Subsequent changes to environment variables will be ignored, and all configuration updates must be made through the HMI interface or by directly editing <code>db/db_config.json</code>.
</p>

</div>

### Creating the .env File

<div style="background: #f8f9fa; border-left: 5px solid #4caf50; padding: 1.5em; margin: 1.5em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; font-weight: 400;">
Create a <code>.env</code> file in the root directory of your PyAutomation installation. This file should contain the database configuration variables.
</p>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0 0; font-weight: 500;">
<strong>File Location</strong>: Place the <code>.env</code> file in the same directory where PyAutomation is installed (typically the project root).
</p>

</div>

### Environment Variables for Database Configuration

#### Database Type

**`AUTOMATION_DB_TYPE`** (optional, default: `sqlite`)

Specifies the type of database to connect to. Valid values:

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0.5em 0; padding-left: 1.5em; font-weight: 400;">
<li><code>sqlite</code> - SQLite file-based database (default)</li>
<li><code>postgresql</code> - PostgreSQL database</li>
<li><code>mysql</code> - MySQL or MariaDB database</li>
</ul>

#### Configuration for SQLite

When using SQLite (`AUTOMATION_DB_TYPE=sqlite`):

**`AUTOMATION_DB_FILE`** (optional, default: `app.db`)

The filename for the SQLite database file. PyAutomation will create this file if it doesn't exist.

**Example .env for SQLite:**

```ini
AUTOMATION_DB_TYPE=sqlite
AUTOMATION_DB_FILE=pyautomation.db
```

#### Configuration for PostgreSQL/MySQL

When using PostgreSQL or MySQL, the following variables are required:

**`AUTOMATION_DB_HOST`** (optional, default: `127.0.0.1`)

The IP address or hostname of the database server.

**`AUTOMATION_DB_PORT`** (optional, defaults: `5432` for PostgreSQL, `3306` for MySQL)

The network port where the database service is listening.

**`AUTOMATION_DB_USER`** (**required**)

The database username with appropriate permissions to create tables and perform read/write operations.

**`AUTOMATION_DB_PASSWORD`** (**required**)

The authentication password for the specified database user.

**`AUTOMATION_DB_NAME`** (**required**)

The name of the database instance. **Important**: The database must already exist on the server before PyAutomation can connect to it.

### Configuration Examples

#### Example 1: PostgreSQL Configuration

```ini
AUTOMATION_DB_TYPE=postgresql
AUTOMATION_DB_HOST=192.168.1.108
AUTOMATION_DB_PORT=5432
AUTOMATION_DB_USER=postgres
AUTOMATION_DB_PASSWORD=your_secure_password
AUTOMATION_DB_NAME=app_db
```

#### Example 2: PostgreSQL with Custom Port

```ini
AUTOMATION_DB_TYPE=postgresql
AUTOMATION_DB_HOST=db.example.com
AUTOMATION_DB_PORT=32800
AUTOMATION_DB_USER=pyautomation_user
AUTOMATION_DB_PASSWORD=your_secure_password
AUTOMATION_DB_NAME=production_db
```

#### Example 3: MySQL Configuration

```ini
AUTOMATION_DB_TYPE=mysql
AUTOMATION_DB_HOST=127.0.0.1
AUTOMATION_DB_PORT=3306
AUTOMATION_DB_USER=automation_user
AUTOMATION_DB_PASSWORD=your_secure_password
AUTOMATION_DB_NAME=pyautomation_db
```

#### Example 4: SQLite Configuration

```ini
AUTOMATION_DB_TYPE=sqlite
AUTOMATION_DB_FILE=app.db
```

### Bootstrap Process

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
When PyAutomation starts for the first time with environment variables configured:
</p>

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Detection</strong>: PyAutomation checks if <code>db/db_config.json</code> exists</li>
<li><strong>Environment Read</strong>: If no configuration file exists, it reads the <code>AUTOMATION_DB_*</code> environment variables</li>
<li><strong>Configuration Creation</strong>: Creates <code>db/db_config.json</code> with the values from environment variables</li>
<li><strong>Connection</strong>: Establishes connection to the database using the new configuration</li>
<li><strong>Database Initialization</strong>: Automatically creates all required database tables, schemas, roles, and the internal <code>system</code> user account</li>
<li><strong>Ready</strong>: PyAutomation is now ready to use with persistent data storage</li>
</ol>

</div>

### Important Notes

<div style="background: #fff3e0; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #ff9800;">

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>One-Time Bootstrap</strong>: This bootstrap process only runs once, on the first startup. After <code>db/db_config.json</code> is created, environment variables are ignored for database configuration.</li>
<li><strong>HMI Configuration Takes Precedence</strong>: Once you configure the database through the HMI interface, those settings are saved to <code>db/db_config.json</code> and will override any future environment variable changes.</li>
<li><strong>Manual Configuration</strong>: If you prefer to configure the database through the HMI interface from the start, you can start PyAutomation without the environment variables and use the configuration bar in the top navigation.</li>
<li><strong>Security</strong>: Never commit <code>.env</code> files containing passwords to version control. Add <code>.env</code> to your <code>.gitignore</code> file.</li>
<li><strong>Database Pre-requisites</strong>: For PostgreSQL and MySQL, ensure the database instance already exists on the server before starting PyAutomation. The bootstrap process will create tables and schemas, but not the database itself.</li>
</ul>

</div>

### After Initial Bootstrap

<div style="background: #f8f9fa; border-left: 5px solid #4caf50; padding: 1.5em; margin: 1.5em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
After the initial bootstrap configuration:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>All database configuration changes should be made through the <strong>Database Configuration</strong> section in the HMI interface</li>
<li>Changes made via the HMI are automatically saved to <code>db/db_config.json</code></li>
<li>On application restart, PyAutomation will use the configuration from <code>db/db_config.json</code>, not environment variables</li>
<li>This ensures that operator-driven configuration changes are preserved across restarts, even if container or environment variables change</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; font-weight: 400;">
This pattern provides a clean "infrastructure-driven" first configuration for automated deployments while allowing operators to adjust database settings later from the HMI interface without being overridden by environment variables.
</p>

</div>

---

## Supported Database Types

<div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #4caf50;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0 0 1.5em 0; font-weight: 500;">
PyAutomation supports connections to the following relational database management systems:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>PostgreSQL</strong>: Recommended for production environments. Offers excellent performance, reliability, and advanced features.</li>
<li><strong>MySQL</strong>: Widely used open-source database with good performance characteristics.</li>
<li><strong>SQLite</strong>: Lightweight file-based database suitable for development and small-scale deployments.</li>
</ul>

</div>

---

## Connection Configuration

<div style="background: #f8f9fa; border-left: 5px solid #2196f3; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 500;">
To establish a connection to your database, configure the following parameters in the database configuration bar located at the top of the application interface.
</p>

</div>

### Step 1: Select Database Type

Click on the first dropdown field in the database configuration bar to select your database type.

![Database Type Selection](../images/DBTypeConfig.png)

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
Available options:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Postgres</strong>: For PostgreSQL databases</li>
<li><strong>MySQL</strong>: For MySQL/MariaDB databases</li>
<li><strong>SQLite</strong>: For SQLite file-based databases</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; font-weight: 400;">
Select the appropriate option based on your database server type. The selected value will be displayed in the dropdown field.
</p>

</div>

### Step 2: Configure Database Name

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 400;">
In the second field, enter the name of the database instance that PyAutomation should connect to.
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Important</strong>: The database must already exist on your database server before connecting</li>
<li>Example: <code>app_db</code>, <code>pyautomation_db</code>, <code>production_db</code></li>
</ul>

</div>

### Step 3: Configure Host Address

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 400;">
Enter the IP address or hostname of the server where your database is hosted.
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Localhost</strong>: Use <code>127.0.0.1</code> or <code>localhost</code> if the database is running on the same machine as PyAutomation</li>
<li><strong>Remote Server</strong>: Enter the specific IP address (e.g., <code>192.168.1.108</code>) or fully qualified domain name (FQDN)</li>
<li><strong>Network Requirements</strong>: Ensure the database server is accessible over the network and that firewalls allow connections on the specified port</li>
</ul>

</div>

### Step 4: Configure Port Number

Specify the network port number where your database service is listening for connections.

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Default Ports:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>PostgreSQL</strong>: <code>5432</code></li>
<li><strong>MySQL</strong>: <code>3306</code></li>
<li><strong>SQLite</strong>: Not applicable (file-based)</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; font-weight: 400;">
<strong>Custom Ports</strong>: If your database server uses a non-standard port, enter the custom port number (e.g., <code>32800</code>).
</p>

</div>

### Step 5: Configure Username

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 400;">
Enter the database username that has the necessary permissions to read from and write to the PyAutomation database.
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>The user must have <strong>CREATE</strong>, <strong>SELECT</strong>, <strong>INSERT</strong>, <strong>UPDATE</strong>, and <strong>DELETE</strong> permissions</li>
<li>For PostgreSQL, ensure the user has schema creation privileges if tables need to be created automatically</li>
<li>Example usernames: <code>postgres</code>, <code>pyautomation_user</code>, <code>admin</code></li>
</ul>

</div>

### Step 6: Configure Password

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 400;">
Enter the authentication password for the specified database user.
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>The password field masks the entered characters for security</li>
<li>Ensure the password is correct, as incorrect credentials will prevent connection</li>
<li>For security best practices, use strong passwords and consider using database-specific credential management</li>
</ul>

</div>

---

## Establishing Connection

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 2em 0; border: 2px solid #4caf50;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
Once all configuration parameters are entered:
</p>

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Verify All Fields</strong>: Double-check that all fields contain valid values</li>
<li><strong>Check Network Connectivity</strong>: Ensure PyAutomation can reach the database server on the specified host and port</li>
<li><strong>Click Connect</strong>: The connection is typically established automatically when you navigate away from the fields, or you may need to click a connect button if available</li>
<li><strong>Monitor Connection Status</strong>: The connection indicator (plug icon) in the top bar will change state to reflect the connection status</li>
</ol>

</div>

![Database Configuration with Connection](../images/DatabaseConfigInNavBar.png)

## Connection Status Indicator

<div style="background: #f8f9fa; border-left: 5px solid #2196f3; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
The database connection status is indicated by the plug icon button in the top navigation bar:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Connected (Red Button)</strong>: When hovering over the red plug icon, a tooltip displays "Disconnect from database", indicating an active connection</li>
<li><strong>Disconnected</strong>: The button appearance changes when no connection is established</li>
</ul>

</div>

### Disconnecting from Database

<div style="background: #ffebee; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #f44336;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
To terminate the database connection:
</p>

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>Locate the plug icon button in the top navigation bar</li>
<li>Click the button to disconnect</li>
<li>PyAutomation will stop writing data to the database until a new connection is established</li>
</ol>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; font-weight: 500;">
<strong>Important</strong>: Disconnecting from the database will interrupt data logging. Historical data collection will resume once you reconnect.
</p>

</div>

---

## Configuration Workflow

<div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0 0 1.5em 0; font-weight: 500;">
Follow this recommended workflow for setting up your database connection:
</p>

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Prepare Your Database Server</strong>
    <ul style="margin-top: 0.5em; margin-bottom: 0.5em;">
    <li>Install and configure your chosen database system (PostgreSQL, MySQL, or SQLite)</li>
    <li>Create the database instance with an appropriate name</li>
    <li>Create a database user with the required permissions</li>
    </ul>
</li>
<li><strong>Gather Connection Information</strong>
    <ul style="margin-top: 0.5em; margin-bottom: 0.5em;">
    <li>Database type (PostgreSQL, MySQL, or SQLite)</li>
    <li>Database name</li>
    <li>Host IP address or hostname</li>
    <li>Port number (if using non-default)</li>
    <li>Username and password</li>
    </ul>
</li>
<li><strong>Configure in PyAutomation</strong>
    <ul style="margin-top: 0.5em; margin-bottom: 0.5em;">
    <li>Open PyAutomation and locate the database configuration bar at the top</li>
    <li>Fill in all required fields in order</li>
    <li>Verify the connection is established (check the connection indicator)</li>
    </ul>
</li>
<li><strong>Verify Data Storage</strong>
    <ul style="margin-top: 0.5em; margin-bottom: 0.5em;">
    <li>Perform actions that generate data (tag updates, alarms, events)</li>
    <li>Verify that data is being written to the database</li>
    <li>Check database tables to confirm data persistence</li>
    </ul>
</li>
</ol>

</div>

---

## Best Practices

<div style="background: #f8f9fa; border-left: 5px solid #4caf50; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Production Environments</strong>: Use PostgreSQL or MySQL for production deployments requiring high availability and performance</li>
<li><strong>Development</strong>: SQLite is convenient for development and testing due to its simplicity</li>
<li><strong>Network Security</strong>: Use VPN or secure network connections when connecting to remote databases</li>
<li><strong>Credentials Management</strong>: Store database credentials securely and avoid hardcoding passwords</li>
<li><strong>Backup Strategy</strong>: Implement regular database backups to protect historical data</li>
<li><strong>Connection Monitoring</strong>: Monitor the connection status regularly to ensure continuous data logging</li>
<li><strong>Firewall Configuration</strong>: Ensure firewall rules allow connections between PyAutomation and the database server</li>
<li><strong>User Permissions</strong>: Create dedicated database users with minimal required permissions rather than using administrative accounts</li>
</ul>

</div>

---

## Troubleshooting

### Connection Failures

<div style="background: #ffebee; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #f44336;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
If you cannot establish a connection:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Verify Network Connectivity</strong>: Use network tools (ping, telnet) to verify the database server is reachable</li>
<li><strong>Check Firewall Settings</strong>: Ensure the database port is open in firewall rules</li>
<li><strong>Validate Credentials</strong>: Double-check username and password are correct</li>
<li><strong>Database Server Status</strong>: Verify the database service is running and listening on the specified port</li>
<li><strong>Database Existence</strong>: Confirm the database name exists on the server</li>
<li><strong>User Permissions</strong>: Ensure the database user has the necessary permissions</li>
</ul>

</div>

### Connection Drops

<div style="background: #fff3e0; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #ff9800;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
If the connection disconnects unexpectedly:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Check Network Stability</strong>: Investigate network connectivity issues</li>
<li><strong>Database Server Status</strong>: Verify the database server is still running</li>
<li><strong>Connection Timeouts</strong>: Some databases may close idle connections; check timeout settings</li>
<li><strong>Resource Limits</strong>: Ensure the database server has sufficient resources (memory, connections)</li>
</ul>

</div>

---

## Data Persistence

<div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #4caf50;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0 0 1.5em 0; font-weight: 500;">
Once connected, PyAutomation will automatically:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1.5em 0; padding-left: 1.5em; font-weight: 400;">
<li>Create necessary database tables and schemas (if they don't exist)</li>
<li>Store historical tag values based on configured logging intervals</li>
<li>Record alarm events and acknowledgments</li>
<li>Log operational events and user actions</li>
<li>Maintain referential integrity between related data entities</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; font-weight: 400;">
Historical data will be available for reporting, analysis, and visualization through PyAutomation's reporting and trending features.
</p>

</div>
