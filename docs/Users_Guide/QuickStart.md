# Quick Start: Running PyAutomation with HMI using Docker

<div align="center" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; padding: 3em 2em; margin: 2em 0; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">

<h2 style="color: white; font-size: 2.5em; margin-bottom: 0.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">
  🚀 From Zero to Production in Minutes
</h2>

<p style="color: white; font-size: 1.4em; margin-top: 1em; font-weight: 300; text-shadow: 1px 1px 2px rgba(0,0,0,0.3);">
  Complete Docker Deployment Guide for PyAutomation 2.0.0
</p>

</div>

This Quick Start guide walks you through bringing up a fully functional PyAutomation instance (backend + HMI) using Docker, and performing the minimum configuration needed to operate the system end‑to‑end.

It is aimed at engineers and operators who want to go from zero to a working system as quickly as possible, while still following production‑grade practices.

<div style="background: #eef7ff; border-left: 5px solid #1976d2; padding: 1.2em 1.5em; margin: 2em 0; border-radius: 6px; color: #0f172a; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
<p style="margin: 0; font-weight: 700;">📌 Note</p>
<p style="margin: 0.35em 0 0 0; font-weight: 500;">
Throughout this guide we assume you are working on a single host (your laptop or a server) and have Docker and Docker Compose installed.
</p>
</div>

![OPC UA Client Screen](images/OPCUAClientScreen.png)

*Figure 0: PyAutomation HMI showing OPC UA client connections and database integration*

---


## 🎯 🐳 1. End-to-End Demo Stack with Docker (DB + OPC UA Simulator + PyAutomation)

<div style="background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #ff9800;">

<h3 style="color: #e65100; font-size: 1.8em; margin-bottom: 1em;">
  🧪 Complete Test Environment
</h3>

<p style="font-size: 1.1em; color: #d84315; margin-bottom: 1.5em;">
  For a complete test environment, the recommended way to run PyAutomation (including the HMI) is to use the provided <code>docker-compose.yml</code> in the project root: PyAutomation provides a <code>docker-compose.yml</code> file that starts:
</p>

</div>

- A **PostgreSQL database** (`db` service).
- An **OPC UA simulation server** (`opcua_server_simulator` service).
- The **PyAutomation automation + HMI** container (`automation` service).

<div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 1em; margin: 1.5em 0; border-radius: 4px;">

<p style="margin: 0; font-weight: 600; color: #856404;">📝 Configuration File Required</p>

<p style="margin: 0.5em 0 0 0; color: #856404; font-size: 0.95em; line-height: 1.6;">
Before deploying the demo stack, you <strong>must create a <code>.env</code> file</strong> in the same directory as your <code>docker-compose.yml</code> file. This configuration file is essential for both <strong>development and production deployments</strong> as it contains all the environment variables needed to configure PyAutomation.
</p>

<p style="margin: 0.8em 0 0 0; color: #856404; font-size: 0.95em; line-height: 1.6;">
Create a <code>.env</code> file in your deployment folder with the following variables (adjust values according to your environment):
</p>

</div>

```ini
AUTOMATION_PORT=8050                  # default 8050         
AUTOMATION_VERSION=2.0.3              # default latest
AUTOMATION_OPCUA_SERVER_PORT=53530    # default 53530
AUTOMATION_HMI_PORT=5000
AUTOMATION_APP_SECRET_KEY="12DFW7HJHJWER6W73338343-FEDF94-EF9EF-EFR9ER"
AUTOMATION_SUPERUSER_PASSWORD="super_ultra_secret_password"
AUTOMATION_DB_TYPE=postgresql
AUTOMATION_DB_HOST=xxx.xxx.xxx.xxx    # It's important change for your host ip
AUTOMATION_DB_PORT=5432
AUTOMATION_DB_USER=postgres
AUTOMATION_DB_PASSWORD=postgres
AUTOMATION_DB_NAME=app_db
```

<div style="background: #e8f5e9; border-left: 4px solid #4caf50; padding: 1em; margin: 1.5em 0; border-radius: 4px;">

<p style="margin: 0; font-weight: 600; color: #2e7d32;">💡 Important Notes:</p>

<ul style="margin: 0.5em 0 0 1.5em; color: #1b5e20; line-height: 1.8; font-size: 0.95em;">
<li>The <code>.env</code> file must be in the <strong>same directory</strong> as your <code>docker-compose.yml</code> file.</li>
<li>For <strong>production deployments</strong>, ensure you use secure values for <code>AUTOMATION_SUPERUSER_PASSWORD</code> and <code>AUTOMATION_APP_SECRET_KEY</code>.</li>
<li>The <code>AUTOMATION_DB_*</code> variables should match your PostgreSQL database configuration.</li>
<li>Never commit the <code>.env</code> file to version control if it contains sensitive information.</li>
</ul>

</div>

This is the fastest way to try PyAutomation with realistic field data, database, and HMI in a single command.

### 1.1. docker-compose.yml: Services Overview

<div style="background: #eef7ff; border-left: 4px solid #1976d2; padding: 0.8em; margin-bottom: 1em; border-radius: 4px;">

<p style="margin: 0; font-size: 0.95em; color: #0f172a;">
<strong>📥 Download Files:</strong> This file (<code>docker-compose.yml</code>) and other required configuration files can be downloaded in <a href="#32-download-required-files" style="color: #1976d2; font-weight: 600;">section 1.2</a> below.
</p>

</div>

The `docker-compose.yml` file defines three services:

```yaml
services:

  db:
    container_name: app_db
    image: "postgres:17-bullseye"
    restart: always
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "7"
    ports:
      - ${AUTOMATION_DB_PORT:-5432}:5432
    environment:
      POSTGRES_PASSWORD: ${AUTOMATION_DB_PASSWORD:-postgres}
      POSTGRES_USER: ${AUTOMATION_DB_USER:-postgres}
      POSTGRES_DB: ${AUTOMATION_DB_NAME:-app_db}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 3

  opcua_server_simulator:
    container_name: opcua_server_simulator
    restart: always
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "7"
    image: "knowai/opcua_server_simulator:2.2.1"
    ports:
      - 0.0.0.0:5015:5015
      - 0.0.0.0:4840:4840
    environment:
      - APP_THREADS=5
      - APP_PORT=5015
      - ASYNC_APP=0
    healthcheck:
      test: curl --fail -s -k http://0.0.0.0:5015/api/healthcheck/ || exit 1
      interval: 15s
      timeout: 10s
      retries: 5
    volumes:
      - ./opcua_server_simulator.yml:/app/app/config.yml
      - ./data_for_tests.csv:/app/app/data/data_for_tests.csv

  automation:
    container_name: "Automation"
    image: "knowai/automation:${AUTOMATION_VERSION:-latest}"
    restart: always
    ports:
      # Backend API (Flask/Gunicorn)
      - ${AUTOMATION_PORT:-8050}:${AUTOMATION_PORT:-8050}
      # HMI frontend served by Nginx inside the container (listen 3000)
      - ${AUTOMATION_HMI_PORT:-3000}:3000
    volumes:
      - automation_db:/app/db
      - automation_logs:/app/logs
    logging:
      driver: "json-file"
      options:
        max-size: "10m" # Rota cuando llega a 10MB
        max-file: "3" # Guarda máximo 3 archivos (30MB total)
    environment:
      AUTOMATION_OPCUA_SERVER_PORT: ${AUTOMATION_OPCUA_SERVER_PORT:-53530}
      AUTOMATION_APP_SECRET_KEY: ${AUTOMATION_APP_SECRET_KEY:-073821603fcc483f9afee3f1500782a4}
      AUTOMATION_SUPERUSER_PASSWORD: ${AUTOMATION_SUPERUSER_PASSWORD:-super_ultra_secret_password}
      AUTOMATION_DB_TYPE: ${AUTOMATION_DB_TYPE:-postgresql}
      AUTOMATION_DB_HOST: ${AUTOMATION_DB_HOST:-127.0.0.1}
      AUTOMATION_DB_PORT: ${AUTOMATION_DB_PORT:-5432}
      AUTOMATION_DB_NAME: ${AUTOMATION_DB_NAME:-app_db}
      AUTOMATION_DB_USER: ${AUTOMATION_DB_USER:-postgres}
      AUTOMATION_DB_PASSWORD: ${AUTOMATION_DB_PASSWORD:-postgres}
    tmpfs:
      - /tmp:size=500k
    depends_on:
      db:
        condition: service_healthy
      opcua_server_simulator:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 256M
    healthcheck:
      test: ["CMD", "python", "/app/healthcheck.py"]
      interval: 15s
      timeout: 10s
      retries: 3

volumes:
  automation_db:
  automation_logs:


```

At a glance:

- `db` exposes PostgreSQL on `localhost:32800` with database `app_db` and user `postgres`.
- `opcua_server_simulator` runs an industrial‑oriented OPC UA simulator with:
  - HTTP API (`APP_PORT=5015`) and healthcheck.
  - OPC UA endpoint on port `4840`.
  - Configuration and data injected via `opcua_server_simulator.yml` and `data_for_tests.csv`.
- `automation` is the same PyAutomation service described in section 1, wired to the simulator and DB.

<div style="background: #fff7e6; border-left: 5px solid #ef6c00; padding: 1.2em 1.5em; margin: 1.5em 0; border-radius: 6px; color: #0f172a;">
<p style="margin: 0; font-weight: 700;">💡 Tip</p>
<p style="margin: 0.35em 0 0 0; font-weight: 500;">
This stack is ideal for demos, automated tests, and onboarding workshops.
</p>
</div>


### 1.2. Download Required Files

To run the demo stack, you need to download the following configuration and data files. **Download all files to the same directory** to ensure everything works together:

<div style="background: #e8f5e9; border-left: 5px solid #4caf50; padding: 1.5em; margin: 1.5em 0; border-radius: 6px; color: #0f172a;">

<p style="margin: 0 0 1em 0; font-weight: 700; font-size: 1.1em;">📥 Download All Files</p>

<div style="background: #fff3cd; border: 2px solid #ffc107; border-radius: 8px; padding: 1em; margin-bottom: 1.5em;">
<p style="margin: 0; font-weight: 600; color: #856404; font-size: 0.95em;">
💡 <strong>Quick Setup:</strong> Create a new folder (e.g., <code>pyautomation-demo</code>), download all three files below to that folder, then follow the deployment instructions in section 1.2.1.
</p>
</div>

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1em; margin-top: 1em;">

<div style="background: white; border: 2px solid #4caf50; border-radius: 8px; padding: 1.2em; box-shadow: 0 2px 6px rgba(0,0,0,0.1);">
<p style="margin: 0 0 0.5em 0; font-weight: 600; color: #2e7d32;">🐳 Docker Compose</p>
<p style="margin: 0 0 0.8em 0; font-size: 0.9em; color: #4a5568;">Main orchestration file for the demo stack</p>
<a href="../../files/docker-compose.yml" download style="display: inline-block; background: #4caf50; color: white; padding: 0.5em 1em; border-radius: 5px; text-decoration: none; font-weight: 600; font-size: 0.9em;">Download docker-compose.yml</a>
</div>

<div style="background: white; border: 2px solid #4caf50; border-radius: 8px; padding: 1.2em; box-shadow: 0 2px 6px rgba(0,0,0,0.1);">
<p style="margin: 0 0 0.5em 0; font-weight: 600; color: #2e7d32;">📄 OPC UA Simulator Config</p>
<p style="margin: 0 0 0.8em 0; font-size: 0.9em; color: #4a5568;">Configuration file for the OPC UA server simulator</p>
<a href="../../files/opcua_server_simulator.yml" download style="display: inline-block; background: #4caf50; color: white; padding: 0.5em 1em; border-radius: 5px; text-decoration: none; font-weight: 600; font-size: 0.9em;">Download opcua_server_simulator.yml</a>
</div>

<div style="background: white; border: 2px solid #4caf50; border-radius: 8px; padding: 1.2em; box-shadow: 0 2px 6px rgba(0,0,0,0.1);">
<p style="margin: 0 0 0.5em 0; font-weight: 600; color: #2e7d32;">📊 Test Data CSV</p>
<p style="margin: 0 0 0.8em 0; font-size: 0.9em; color: #4a5568;">Sample data file for the OPC UA simulator</p>
<a href="../../files/data.csv" download style="display: inline-block; background: #4caf50; color: white; padding: 0.5em 1em; border-radius: 5px; text-decoration: none; font-weight: 600; font-size: 0.9em;">Download data.csv</a>
</div>

</div>

<p style="margin: 1.5em 0 0 0; font-size: 0.95em; color: #4a5568;">
<strong>Important:</strong> All three files must be in the <strong>same directory</strong>. The <code>docker-compose.yml</code> file references the other two files using relative paths (<code>./opcua_server_simulator.yml</code> and <code>./data.csv</code>).
</p>

</div>

#### 1.2.1. Deployment Instructions

Once you have downloaded all three files to the same directory, follow these steps to deploy the complete demo stack:

<div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #2196f3;">

<h4 style="color: #1976d2; font-size: 1.3em; margin-bottom: 1em;">🚀 Quick Deployment Steps</h4>

<div style="background: white; border-radius: 8px; padding: 1.5em; margin-bottom: 1.5em; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">

<p style="margin: 0 0 1em 0; font-weight: 600; color: #1565c0;">Step 1: Navigate to your files directory</p>

```bash
cd pyautomation-demo  # or whatever folder you created
```

<p style="margin: 1em 0 0 0; font-weight: 600; color: #1565c0;">Step 2: Verify all files are present</p>

```bash
ls -la
# You should see:
# - docker-compose.yml
# - opcua_server_simulator.yml
# - data_for_tests.csv
```

<p style="margin: 1em 0 0 0; font-weight: 600; color: #1565c0;">Step 3: Create a .env file</p>

<p style="margin: 0.5em 0 1em 0; color: #4a5568; font-size: 0.95em;">
You must create a <code>.env</code> file to customize ports and credentials, or use the default values defined in <code>docker-compose.yml</code>.
</p>

```ini
AUTOMATION_PORT=8050                  # default 8050         
AUTOMATION_VERSION=2.0.3              # default latest
AUTOMATION_OPCUA_SERVER_PORT=53530    # default 53530
AUTOMATION_HMI_PORT=5000
AUTOMATION_APP_SECRET_KEY="12DFW7HJHJWER6W73338343-FEDF94-EF9EF-EFR9ER"
AUTOMATION_SUPERUSER_PASSWORD="super_ultra_secret_password"
AUTOMATION_DB_TYPE=postgresql
AUTOMATION_DB_HOST=xxx.xxx.xxx.xxx    # It's important change for your host ip
AUTOMATION_DB_PORT=5432
AUTOMATION_DB_USER=postgres
AUTOMATION_DB_PASSWORD=postgres
AUTOMATION_DB_NAME=app_db
```

<p style="margin: 1em 0 0 0; font-weight: 600; color: #1565c0;">Step 4: Start the demo stack</p>

```bash
docker compose --env-file .env up -d
```

<p style="margin: 1em 0 0 0; font-weight: 600; color: #1565c0;">Step 5: Check service status</p>

```bash
docker compose ps
```

<p style="margin: 1em 0 0 0; font-weight: 600; color: #1565c0;">Step 6: View logs</p>


```bash
docker compose logs -f automation
```

<p style="margin: 1em 0 0.5em 0; font-weight: 600; color: #0f172a; font-size: 0.95em;">If everything is working correctly, you should see output similar to this:</p>

```
Automation  | 2025-12-19 00:32:19,939 INFO Set uid to user 0 succeeded
Automation  | 2025-12-19 00:32:19,942 INFO supervisord started with pid 1
Automation  | 2025-12-19 00:32:20,946 INFO spawned: 'nginx' with pid 7
Automation  | 2025-12-19 00:32:20,948 INFO spawned: 'backend' with pid 8
Automation  | 2025-12-19 00:32:22,873 INFO success: nginx entered RUNNING state, process has stayed up for > than 1 seconds (startsecs)
Automation  | 2025-12-19 00:32:31,722 INFO success: backend entered RUNNING state, process has stayed up for > than 10 seconds (startsecs)
```

<p style="margin: 1em 0 0 0; font-weight: 600; color: #1565c0;">Step 7: View backend logs</p>

```bash
docker exec -it Automation tail -n 100 /var/log/supervisor/backend.out.log
```

<p style="margin: 1em 0 0.5em 0; font-weight: 600; color: #0f172a; font-size: 0.95em;">If everything is working correctly, you should see backend application logs here.</p>

```
[WARNING] -  Not Found service without SSL Certificate
[OK] - Worker connections: 100
[OK] - Number of workers: 1
[INFO] 2025-12-19 00:48:33 Starting app with configuration:
[INFO] 2025-12-19 00:48:33 Logger period: 10.0 seconds
[INFO] 2025-12-19 00:48:33 Log max bytes: 10485760 bytes
[INFO] 2025-12-19 00:48:33 Log backup count: 3 backups
[INFO] 2025-12-19 00:48:33 Log level: 20
[INFO] 2025-12-19 00:48:34 App started successfully
```

</div>

<div style="background: #e8f5e9; border-left: 4px solid #4caf50; padding: 1em; margin-top: 1.5em; border-radius: 4px;">

<p style="margin: 0; font-weight: 600; color: #2e7d32;">✅ Once running, access the services:</p>

<ul style="margin: 0.5em 0 0 1.5em; color: #1b5e20; line-height: 1.8;">
<li><strong>PyAutomation HMI:</strong> <code>http://localhost:3000</code> (or the port specified in your <code>AUTOMATION_HMI_PORT</code> environment variable)</li>
<li><strong>PyAutomation API:</strong> <code>http://localhost:8050/api/docs</code> (or the port specified in your <code>AUTOMATION_PORT</code> environment variable)</li>
<li><strong>OPC UA Server:</strong> <code>opc.tcp://localhost:4840</code></li>
<li><strong>OPC UA Simulator API:</strong> <code>http://localhost:5015/api/docs</code></li>
</ul>

</div>

<div style="background: #eef7ff; border-left: 4px solid #1976d2; padding: 1em; margin-top: 1.5em; border-radius: 4px;">

<p style="margin: 0; font-weight: 600; color: #0f172a;">🔐 Superuser Account Created</p>

<p style="margin: 0.5em 0 0 0; color: #0f172a; font-size: 0.95em; line-height: 1.6;">
During the initial startup, PyAutomation automatically creates a <strong>superuser account</strong> with the following credentials:
</p>

<ul style="margin: 0.5em 0 0 1.5em; color: #0f172a; line-height: 1.8; font-size: 0.95em;">
<li><strong>Username:</strong> <code>system</code></li>
<li><strong>Password:</strong> The value configured in your <code>AUTOMATION_SUPERUSER_PASSWORD</code> environment variable (from your <code>.env</code> file)</li>
</ul>

<p style="margin: 0.8em 0 0 0; color: #0f172a; font-size: 0.95em; line-height: 1.6;">
You can use these credentials to log in to the PyAutomation HMI at <code>http://localhost:3000</code> (or your configured HMI port). This superuser account has full administrative privileges and is intended for initial setup, creating additional users, and system recovery.
</p>

<p style="margin: 0.8em 0 0 0; color: #0f172a; font-size: 0.9em; line-height: 1.6; font-style: italic;">
<strong>Security Note:</strong> Change the <code>AUTOMATION_SUPERUSER_PASSWORD</code> value in your <code>.env</code> file from the default before deploying to production environments.
</p>

</div>

<div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 1em; margin-top: 1.5em; border-radius: 4px;">

<p style="margin: 0; font-weight: 600; color: #856404;">🛑 To stop the demo stack:</p>

```bash
docker compose down
```

<p style="margin: 0.5em 0 0 0; color: #856404; font-size: 0.95em;">
To remove volumes (database data) as well, use: <code>docker compose down -v</code>
</p>

</div>

</div>

### 1.3. OPC UA Simulator Configuration: opcua_server_simulator.yml

The OPC UA simulator uses a YAML configuration file mounted into the container:

```yaml
version: "3.3"

filename: "data_for_tests"
separator: ","
header: [0]
interval: 1.0
variables:
  FI_01:
    name: "FIRST_TRANSMITTER_MASS_FLOW"
    uncertainty: 0.1
    min: 0
    max: 200
  PI_01:
    name: "FIRST_TRANSMITTER_PRESSURE"
    uncertainty: 0.1
    min: 200000
    max: 1200000
  # ... other variables ...
server_folder_namespace: iDetectFugas
```

Key fields:

- `filename`: **base name** of the CSV file without extension. Here it is `data_for_tests`, which matches `data_for_tests.csv`.
- `separator`: column separator used in the CSV file (`,` in this case).
- `header: [0]`: indicates that the **first row** (index 0) in the CSV contains column headers.
- `interval`: time in seconds between updates (e.g., `1.0` means new values every 1 second).
- `variables`: dictionary of **OPC UA variables** the simulator will expose:
  - Keys like `FI_01`, `PI_01`, etc. map to tags/nodes.
  - `name`: human‑readable description.
  - `min`, `max`: value ranges used to generate or normalize data.
  - `uncertainty`: percentage uncertainty / noise to apply.
- `server_folder_namespace`: top‑level namespace folder under which the variables appear in the OPC UA address space.

The simulator uses this configuration plus the CSV file to drive the time series it serves.

![OPC UA Explorer](images/OPCUAExplorer.png)

*Figure 3.2: OPC UA namespace tree showing variables like FI_01, PI_01, etc. from the simulator*

### 1.4. CSV Data Format: data_for_tests.csv

The `data_for_tests.csv` file (mounted into the container) provides the raw time‑series used by the simulator:

- Must be located in the **project root** (as referenced in `docker-compose.yml`).
- Is mounted to `/app/app/data/data_for_tests.csv` inside the container.
- Must match the `filename` specified in `opcua_server_simulator.yml` (`data_for_tests` → `data_for_tests.csv`).

General format:

- **Separator**: comma (`,`), as specified by `separator: ","`.
- **Header row** (row 0): contains column names that the simulator uses to map data.
- **Data rows**: each row represents one time step.
- Numeric columns are interpreted according to the `variables` section in `opcua_server_simulator.yml`.

Conceptually:

```text
timestamp,FI_01,PI_01,DI_01,TI_01,FI_02,PI_02,DI_02,TI_02
2024-01-01T00:00:00Z, 10.0, 250000, 800, 20, 15.0, 260000, 820, 21
2024-01-01T00:00:01Z, 11.2, 252000, 805, 20.1, 15.5, 262000, 825, 21.1
...
```

> The actual `data_for_tests.csv` in the repository may contain different columns and values, but it follows this pattern: a header line plus numerical data compatible with the variables defined in `opcua_server_simulator.yml`.

If you want to customize the simulation:

1. Edit `opcua_server_simulator.yml` to add/remove variables or change ranges.
2. Adjust `data_for_tests.csv` so that:
   - It contains corresponding columns for your variables.
   - Values fall within the desired ranges.

> **Note:** The `data_for_tests.csv` file follows a standard CSV format with a header row and numeric data columns. You can open it in any spreadsheet application (Excel, LibreOffice Calc, etc.) to view and edit the time-series data.

### 1.5. Starting the full demo stack

Once you run your command:

```bash
docker compose --env-file .env up -d
```

This will:

- Start PostgreSQL (`db`).
- Start the OPC UA simulator (`opcua_server_simulator`).
- Start PyAutomation (`automation`) using the same image and environment variables described earlier.

Once all three services are healthy:

- Access the HMI at `http://localhost:${AUTOMATION_HMI_PORT:-3000}` (for example `http://localhost:3000` or `http://localhost:5000` depending on your `.env`).
- Configure the **Database connection** in the HMI to point to the `db` service:
  - Host: `db` (inside Docker network) or `localhost:32800` from the host, depending on your setup.
  - Port: `5432`.
  - Database: `app_db`.
  - User / Password: `postgres` / `postgres` (or your custom values).
- Configure an **OPC UA Client** in the HMI to point to the simulator:
  - Endpoint: `opc.tcp://opcua_server_simulator:4840` (inside Docker network) or `opc.tcp://localhost:4840` from the host.

From this point, you have a realistic test environment with:

- A running database.
- A configurable OPC UA simulator serving data from a CSV file.
- PyAutomation HMI ready to define tags, trends, alarms, and real‑time charts based on that data.

![First Page After Login](images/FirstPageAfterLogin.png)

*Figure 34: Main dashboard after successful login, showing the HMI connected to database and ready for configuration*

---

## 🖥️ 4. First Steps in the HMI

<div style="background: linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #9c27b0;">

<h3 style="color: #7b1fa2; font-size: 1.8em; margin-bottom: 1em;">
  🎨 Getting Started with the Interface
</h3>

<p style="font-size: 1.1em; color: #6a1b9a; margin-bottom: 1.5em;">
  Once the containers are running, open the HMI in your browser.
</p>

</div>

### 4.1. Creating the first user (Signup flow)

User accounts are **created from the Login/Signup screen**.

1. Open the HMI login page (e.g., `http://localhost:8050`).
2. Click on the **Signup** option on the login screen.
3. Fill in the signup form:
   - **Username**
   - **Email**
   - **Password**
   - Optional: **Name** and **Last name**
4. Submit the form. A new user will be created automatically with the **lowest permission level (GUEST / invited user)**.

At this stage, the new user can log in but has **limited permissions**. To promote this user to an operator or admin:

1. Log in using the **superuser** credentials (controlled by `AUTOMATION_SUPERUSER_PASSWORD`).
2. Navigate to **User Management / Users**.
3. Locate the newly created GUEST user.
4. Change the **role** to the appropriate level (e.g., **admin** for the first full‑privilege account).
5. Log out and log back in with the promoted user.

> From this point, you should use admin and operator accounts for daily work, and reserve the superuser only for recovery procedures and role management when no admin is available.

![Signup Screen](images/SignupScreen.png)

*Figure 2: User signup form for creating new accounts*

### 4.2. User login

- Access the login page at `http://localhost:8050`.
- Enter username/email and password.
- If login fails, check:
  - Container logs.
  - That the user is active and has a valid role assigned.

![Login Screen with User](images/LoginScreenWithUser1.png)

*Figure 3: Login page with username/password fields*

---

## 5. Navbar Basics: Language, Theme, Fullscreen

The top navigation bar (navbar) provides quick access to global UI features:

- **Language switch**: Change the UI language (e.g., English / Spanish).
- **Theme toggle**: Switch between light and dark themes.
- **Fullscreen**: Enter / exit fullscreen mode for control room displays.

These settings are purely visual but essential for a comfortable operator experience.

Steps:

1. Locate the language selector and choose your preferred locale.
2. Toggle the theme icon to switch between light and dark modes.
3. Use the fullscreen button when deploying on wall screens or operator stations.

![Navbar Controls](images/ButtonsForLanguageThemesAndFullScreen.png)

*Figure 4: Navbar with language switch, theme toggle, and fullscreen controls*

---

## 6. Connecting to the Database from the HMI

With PostgreSQL running, connect PyAutomation to the database via the HMI:

1. Open the **Database** section from the navbar.
2. Fill in:
   - **Host** (e.g., `localhost` or `postgres` if using Docker network).
   - **Port** (e.g., `5432`).
   - **Database name** (e.g., `automation_db`).
   - **User** and **Password** (e.g., `automation_user` / `your_password`).
3. Click **Connect**.

On success:

- PyAutomation will create all required tables (tags, alarms, users, events, logs, etc.).
- Initial default data (roles, variables, units) will be inserted.

If connection fails, check:

- That the DB container is running and reachable.
- Credentials and DB name.
- Docker network configuration (if using multiple containers).

![Database Configuration](images/DatabaseConfigInNavBar.png)

*Figure 5: Database configuration form in the navbar*

---

## 7. Defining an OPC UA Client (Field Data Connectivity)

To bring real (or simulated) field data into PyAutomation:

1. Go to the **Communications / OPC UA Clients** section.
2. Create a new OPC UA client:
   - **Name**: A descriptive identifier (e.g., `Plant_Simulator`).
   - **Endpoint URL**: e.g., `opc.tcp://opcua-sim:4840/` or `opc.tcp://localhost:4840/`.
   - **Security mode / policy** as appropriate (for a simulator, often `None`).
3. Save the client and establish the connection.
4. Use the OPC UA browser to:
   - Navigate the node tree.
   - Select variables to monitor.
   - Add them as tags into the system (see next section).

![OPC UA Clients](images/OPCUAClientsConnections.png)

*Figure 6: OPC UA client connections management*

![OPC UA Explorer](images/OPCUAExplorer.png)

*Figure 7: OPC UA node explorer for browsing the address space*

![OPC UA Multi-Selection](images/OPCUAExplorerMultiSelection.png)

*Figure 8: Multi-selection of OPC UA nodes using Ctrl+Click*

![Selected Tags with Polling](images/SelectedTagsInOPCUAExplorerWithPollingConnection.png)

*Figure 9: Selected tags in OPC UA explorer with active polling connection*

---

## 8. Tags: Create, Edit, Delete, Export

Tags are the core data points of PyAutomation.

### 8.1. Creating tags

1. Navigate to the **Tags** section.
2. Click **Create** (or equivalent action).
3. For each tag, define:
   - **Name**: Unique identifier.
   - **Variable / Data type / Unit**: Semantic and type information.
   - **OPC UA address** (if linked to a field variable).
   - **Scan time**, deadband, and other filters as needed.
4. Save and verify that live values appear (if connected to OPC UA).

### 8.2. Editing and deleting tags

- Use the **Edit** action to adjust parameters like units, descriptions, or OPC UA bindings.
- Use the **Delete** action to remove unused tags (be aware of dependent alarms, trends, and loggers).

### 8.3. Exporting / importing tags

- Use the **Export** function to download tag definitions (for backup or replication).
- Use **Import** to load predefined tag sets in bulk.

![Tags Empty Page](images/TagsDefinitionEmptyPage.png)

*Figure 10: Tags definition page (empty state)*

![Create Tag Form](images/CreateTagForm.png)

*Figure 11: Create new tag form with basic configuration*

![Create Tag Polling Configuration](images/CreateTagPollingAndFilterConfiguration.png)

*Figure 12: Tag creation form showing polling and filter configuration options*

![Tags Created](images/TagsCreated.png)

*Figure 13: Tags list after creating multiple tags*

![Edit Tag Form](images/EditTagForm.png)

*Figure 14: Edit tag form for modifying existing tag parameters*

---

## 9. DataLogger (Historical Data): Filters and Downloads

The DataLogger module stores tag values for long‑term analysis.

1. Open the **Data Logger / Historical Data** section.
2. Configure:
   - Tags to log.
   - Logging period (sample time).
   - Filters (time ranges, tag subsets).
3. Once historical data is available, use the UI to:
   - Filter by date/time window.
   - Select specific tags.
   - Download data as CSV/Excel for offline analysis.

![DataLogger Empty Table](images/DataLoggerEmptyTable.png)

*Figure 15: DataLogger empty state with no historical data*

![DataLogger Filters](images/DataLoggerFilterSample5Sec.png)

*Figure 16: DataLogger with filters applied (5-second sample time)*

---

## 10. Historical Trends (Trends Module)

Historical trends provide graphical visualization of logged data.

1. Go to the **Trends** section.
2. Select:
   - One or more tags.
   - Time range.
   - Sampling and resampling options (if available).
3. View the plotted trends and adjust:
   - Time window.
   - Zoom, pan, and cursors (if supported).
4. Export underlying data if needed.

![Historical Trends](images/TrendsLastHour.png)

*Figure 17: Historical trends chart showing multiple tags over the last hour*

---

## 11. Alarms: Create, Edit, Delete, Actions, Export

The Alarms module manages process conditions and notifications.

### 11.1. Defining alarms

1. Open the **Alarms** section.
2. Create a new alarm:
   - **Tag**: The process variable to monitor.
   - **Condition**: Threshold (e.g., high, high‑high, low, low‑low).
   - **Classification / Priority / Severity**.
   - **Messages** and optional metadata.
3. Save and test by driving the source tag beyond thresholds.

### 11.2. Managing alarms at runtime

- **Acknowledge** alarms.
- **Shelve / suppress** alarms (if supported) for maintenance.
- Use filters to focus on active, unacknowledged, or historical alarms.
- Export alarm tables to CSV/Excel for reports and audits.

![Alarms Empty Page](images/AlarmDefinitionEmptyPage.png)

*Figure 18: Alarm definition page (empty state)*

![Create Alarm Form](images/CreateNewAlarmForm.png)

*Figure 19: Create new alarm form with tag selection and threshold configuration*

![Edit Alarm Form](images/EditAlarmForm.png)

*Figure 20: Edit alarm form for modifying alarm parameters*

![Alarm History](images/AlarmHistoryPage.png)

*Figure 21: Alarm history page showing active and historical alarms*

---

## 12. Alarm Summary

The Alarm Summary view aggregates alarm information for quick situational awareness.

Key capabilities:

- Filter by:
  - Time window.
  - Classification / Priority.
  - State (active, acknowledged, cleared).
- Use this view to:
  - Identify recurring issues.
  - Evaluate alarm flood situations.
  - Support root cause analysis.

![Alarm Summary](images/AlarmHistoryPage.png)

*Figure 22: Alarm summary view with filters and aggregated alarm information*

---

## 13. Real-Time Trends (HMI Strip Charts)

Real‑time trends (strip charts) are provided by the new HMI module.

### 13.1. Main features

- **Edit / Production modes**:
  - **Edit mode**: Reposition and resize strip charts, configure tags and buffer sizes.
  - **Production mode**: Layout is locked; only visualization is available.
  - Mode switching by double‑clicking anywhere in the RealTimeTrends view.
- **Buffer size**:
  - Each chart has a configurable **buffer size** (number of points kept in memory).
  - Larger buffers show longer histories but require more memory.
- **Tag configuration**:
  - Each chart supports multiple tags.
  - Tags can be grouped by units; up to **two distinct units** per chart (mapped to two Y‑axes).

### 13.2. Configuring real‑time trends

1. Enter **Edit mode** (double‑click in the view).
2. Click **Add Chart** to create a new strip chart.
3. For each chart:
   - Set a descriptive **title**.
   - Use the **Tags** button to:
     - Search tags.
     - Add / remove tags.
     - Adjust **buffer size**.
4. Drag and resize the charts to build your HMI layout.
5. Switch back to **Production mode** (double‑click) to lock the layout.

![Real-Time Trends Empty](images/RealTimeEmptyPage.png)

*Figure 23: Real-time trends page (empty state)*

![Real-Time Edit Mode](images/RealTimeEditMode.png)

*Figure 24: Real-time trends in edit mode for configuring strip charts*

![Search Tags in Strip Chart](images/SearchTagIntoStripChartConfiguration.png)

*Figure 25: Searching and selecting tags for strip chart configuration*

![First Strip Chart Configured](images/FirstStripChartConfigured.png)

*Figure 26: First strip chart configured with selected tags*

![Real-Time Production Mode](images/RealTimeStripChartIntoProductionMode.png)

*Figure 27: Real-time trends in production mode with multiple strip charts displaying live data*

---

## 14. Machines: Actions, Configuration, Export

The Machines module (if enabled in your deployment) models equipment or units in your plant.

Typical operations:

- Configure machine metadata (name, description, associated tags).
- View machine status and KPIs.
- Export machine lists and configurations for documentation or replication.

![Machines Page](images/MachinePage.png)

*Figure 28: Machines page showing state machine configurations and status*

---

## 15. Events: Logging, Filters, Comments, Export

PyAutomation logs system and process events to support traceability and diagnostics.

Capabilities:

- **What is logged**:
  - Alarm state changes.
  - User actions (logins, configuration changes).
  - System events (database connection, communication changes).
- **Filters**:
  - Time range, event type, user, severity.
- **Comments**:
  - Operators can attach comments to events for context and hand‑over.
- **Export**:
  - Download event tables to CSV/Excel for audits and incident analysis.

![Events Page](images/EventPage.png)

*Figure 29: Events page with filters and event history table*

![Add Comment to Event](images/AddCommentEvent.png)

*Figure 30: Adding a comment to an event for context and hand-over*

---

## 16. Operational Logbook (Operational Logs)

The Operational Logbook is used to capture high‑level operational information (beyond raw events and alarms).

Use cases:

- Operator notes during shifts.
- Records of manual interventions.
- Summaries of production issues and resolutions.

Features:

- **Classification** of logs (e.g., maintenance, operations, quality).
+- Advanced **filters** by date, classification, user.
 - **Exports** for monthly / quarterly reporting.

![Operational Logbook](images/OperationalLog.png)

*Figure 31: Operational logbook view with classification filters and log entries*

---

## 17. User Management: Roles, Passwords, Administration

The **Users** module provides robust access control.

### 17.1. Roles and permissions

- Default roles (e.g., admin, operator, viewer) define what each user can do.
- Best practice:
  - Give **admins** full configuration rights.
  - Give **operators** runtime control and acknowledgment permissions.
  - Give **viewers** read‑only access.

### 17.2. Password management

- Admins can:
  - Reset user passwords.
  - Force password changes at next login (if configured).
- Users can:
  - Change their own passwords from the profile or user settings.

### 17.3. Superuser and recovery

- The **superuser** password is controlled by `AUTOMATION_SUPERUSER_PASSWORD` (see section 1.1).
- Use it **only** for:
  - Creating initial admin users.
  - Recovering from a state where no admin can log in.

![User Management](images/UserManagementPage.png)

*Figure 32: User management page showing user list, roles, and password management actions*

---

## 18. System Settings: Logger and Configuration Management

The **Settings** module centralizes system‑level configuration.

Key parameters:

- **Logger Period**: Interval at which log records are flushed or rotated.
- **Log Level**: Verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL).
- **Log Max Bytes**: Maximum size of a single log file before rotation.
- **Log Backup Count**: Number of rotated log files to keep.

Configuration management:

- **Export Configuration**:
  - Download a JSON snapshot of system configuration (tags, alarms, communications, users, etc.).
  - Useful for backups and cloning environments.
- **Import Configuration**:
  - Load a previously exported configuration.
  - Ideal for restoring environments or deploying standardized setups.

Best practices:

- Keep a **versioned archive** of configuration exports.
- Align log levels with environment:
  - `DEBUG` for development.
  - `INFO` or `WARNING` for production.

![System Settings](images/SystemSettingsPage.png)

*Figure 33: System settings page with logger parameters and configuration import/export options*

---

## ✅ 19. Summary

<div align="center" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; padding: 3em 2em; margin: 3em 0; box-shadow: 0 15px 35px rgba(0,0,0,0.2);">

<h2 style="color: white; font-size: 2em; margin-bottom: 1.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">
  🎉 Congratulations! You're Ready to Go
</h2>

<p style="color: white; font-size: 1.3em; line-height: 1.8; margin-bottom: 2em; opacity: 0.95;">
  By following this Quick Start, you should now have:
</p>

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1.5em;">

<div style="background: white; border-radius: 10px; padding: 2em; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
<h4 style="color: #667eea; font-size: 1.3em; margin-bottom: 0.5em;">🐳 PyAutomation Running</h4>
<p style="color: #4a5568; margin: 0;">Backend + HMI running in Docker</p>
</div>

<div style="background: white; border-radius: 10px; padding: 2em; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
<h4 style="color: #667eea; font-size: 1.3em; margin-bottom: 0.5em;">💾 Database Connected</h4>
<p style="color: #4a5568; margin: 0;">PostgreSQL connected and initialized</p>
</div>

<div style="background: white; border-radius: 10px; padding: 2em; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
<h4 style="color: #667eea; font-size: 1.3em; margin-bottom: 0.5em;">🔌 OPC UA Simulator</h4>
<p style="color: #4a5568; margin: 0;">Providing realistic test data</p>
</div>

<div style="background: white; border-radius: 10px; padding: 2em; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
<h4 style="color: #667eea; font-size: 1.3em; margin-bottom: 0.5em;">⚙️ Full Configuration</h4>
<p style="color: #4a5568; margin: 0;">Users, tags, alarms, trends, and logs configured</p>
</div>

</div>

<p style="color: white; font-size: 1.2em; line-height: 1.8; margin-top: 2em; opacity: 0.95;">
  From here, you can refine your configuration, connect to real plant equipment, and tailor the HMI to your operations.
</p>

</div>


