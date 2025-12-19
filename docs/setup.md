# Installation and Setup

<div align="center" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; padding: 3em 2em; margin: 2em 0; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">

<h2 style="color: white; font-size: 2.5em; margin-bottom: 0.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">
  🚀 Get Started with PyAutomation
</h2>

<p style="color: white; font-size: 1.4em; margin-top: 1em; font-weight: 300; text-shadow: 1px 1px 2px rgba(0,0,0,0.3);">
  Quick Setup Guide for Development and Production
</p>

</div>

---

This comprehensive guide covers the installation and configuration of PyAutomation for both **development** and **production** environments. Follow these steps to get PyAutomation up and running in minutes!

---

## 📋 Prerequisites

<div style="background: #f8f9fa; border-left: 5px solid #667eea; padding: 2em; margin: 2em 0; border-radius: 5px;">

<p style="font-size: 1.2em; line-height: 1.8; color: #2d3748; margin-bottom: 1em;">
  Before installing PyAutomation, ensure you have the following installed on your system:
</p>

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5em; margin-top: 1.5em;">

<div style="background: white; border: 2px solid #667eea; border-radius: 10px; padding: 1.5em; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
<h4 style="color: #667eea; font-size: 1.2em; margin-bottom: 0.5em;">🐍 Python</h4>
<p style="color: #4a5568; margin: 0; font-weight: 600;">Version 3.10 or higher</p>
</div>

<div style="background: white; border: 2px solid #667eea; border-radius: 10px; padding: 1.5em; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
<h4 style="color: #667eea; font-size: 1.2em; margin-bottom: 0.5em;">📦 pip</h4>
<p style="color: #4a5568; margin: 0; font-weight: 600;">Python package installer</p>
</div>

<div style="background: white; border: 2px solid #667eea; border-radius: 10px; padding: 1.5em; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
<h4 style="color: #667eea; font-size: 1.2em; margin-bottom: 0.5em;">🔧 Virtualenv</h4>
<p style="color: #4a5568; margin: 0; font-weight: 600;">Optional but recommended</p>
</div>

<div style="background: white; border: 2px solid #667eea; border-radius: 10px; padding: 1.5em; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
<h4 style="color: #667eea; font-size: 1.2em; margin-bottom: 0.5em;">🔀 Git</h4>
<p style="color: #4a5568; margin: 0; font-weight: 600;">Version control system</p>
</div>

</div>

</div>

---

## ⚡ Installation Steps

### Step 1: Clone the Repository

<div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #667eea;">

<p style="font-size: 1.1em; color: #2d3748; margin-bottom: 1em; font-weight: 600;">
  Start by cloning the PyAutomation repository to your local machine:
</p>

```bash
git clone https://github.com/know-ai/PyAutomation.git
cd PyAutomation
```

</div>

---

### Step 2: Set Up a Virtual Environment

<div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #667eea;">

<p style="font-size: 1.1em; color: #2d3748; margin-bottom: 1em;">
  It is <strong>best practice</strong> to run Python applications in a virtual environment to avoid dependency conflicts.
</p>

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1.5em; margin-top: 1.5em;">

<div style="background: white; border-radius: 8px; padding: 1.5em; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
<h4 style="color: #667eea; font-size: 1.1em; margin-bottom: 0.5em;">🐧 Linux/macOS</h4>
```bash
python3 -m venv venv
source venv/bin/activate
```
</div>

<div style="background: white; border-radius: 8px; padding: 1.5em; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
<h4 style="color: #667eea; font-size: 1.1em; margin-bottom: 0.5em;">🪟 Windows</h4>
```powershell
python -m venv venv
.\venv\Scripts\activate
```
</div>

</div>

</div>

---

### Step 3: Install Dependencies

<div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #667eea;">

<p style="font-size: 1.1em; color: #2d3748; margin-bottom: 1em;">
  Install the required Python packages using <code style="background: rgba(102, 126, 234, 0.1); padding: 0.2em 0.4em; border-radius: 4px;">pip</code>:
</p>

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

<div style="background: rgba(102, 126, 234, 0.1); border-left: 4px solid #667eea; padding: 1em; margin-top: 1.5em; border-radius: 4px;">

<p style="margin: 0; color: #4a5568;">
  <strong>💡 Tip:</strong> If you are developing documentation or running tests, you might also want to install additional requirements:
</p>

```bash
pip install -r docs_requirements.txt
```

</div>

</div>

---

## ⚙️ Configuration

### Environment Variables

<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; padding: 2em; margin: 2em 0; color: white; box-shadow: 0 8px 20px rgba(102, 126, 234, 0.3);">

<h3 style="color: white; font-size: 1.8em; margin-bottom: 1em;">
  🔐 Configure Your Environment
</h3>

<p style="font-size: 1.1em; line-height: 1.8; margin-bottom: 1.5em; opacity: 0.95;">
  PyAutomation uses environment variables and configuration files to manage settings. Create a <code style="background: rgba(255,255,255,0.2); padding: 0.2em 0.4em; border-radius: 4px;">.env</code> file in the root directory to configure the application.
</p>

</div>

**Example `.env` file:**

```ini
# Web Server Configuration  
AUTOMATION_PORT=8050                  # default 8050         
AUTOMATION_VERSION=2.0.0             # default latest
AUTOMATION_OPCUA_SERVER_PORT=53530    # default 53530
AUTOMATION_HMI_PORT=5000
AUTOMATION_APP_SECRET_KEY="12DFW7HJHJWER6W73338343-FEDF94-EF9EF-EFR9ER"
AUTOMATION_SUPERUSER_PASSWORD="super_ultra_secret_password"
AUTOMATION_DB_TYPE=postgresql
AUTOMATION_DB_HOST=xxx.xxx.xxx.xxx
AUTOMATION_DB_PORT=5432
AUTOMATION_DB_USER=xxxxxxxx
AUTOMATION_DB_PASSWORD=xxxxxxxxx
AUTOMATION_DB_NAME=xxxxxxx
```

---

### 💾 Database Configuration

<div style="background: #fff3cd; border-left: 5px solid #ffc107; padding: 2em; margin: 2em 0; border-radius: 5px;">

<h3 style="color: #856404; font-size: 1.5em; margin-bottom: 1em;">
  ⚠️ Important: Database Setup Required
</h3>

<p style="font-size: 1.1em; line-height: 1.8; color: #856404; margin-bottom: 1.5em;">
  PyAutomation requires a database to be set up and running <strong>before</strong> you can connect to it through the web configuration interface.
</p>

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1.5em; margin-top: 1.5em;">

<div style="background: white; border: 2px solid #ffc107; border-radius: 10px; padding: 1.5em; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
<h4 style="color: #856404; font-size: 1.2em; margin-bottom: 0.5em;">1️⃣ Create Database</h4>
<p style="color: #4a5568; margin: 0;">
  <strong>SQLite:</strong> No setup required - auto-created<br>
  <strong>PostgreSQL/MySQL:</strong> Create server/instance manually or using Docker
</p>
</div>

<div style="background: white; border: 2px solid #ffc107; border-radius: 10px; padding: 1.5em; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
<h4 style="color: #856404; font-size: 1.2em; margin-bottom: 0.5em;">2️⃣ Connect PyAutomation</h4>
<p style="color: #4a5568; margin: 0;">
  PyAutomation automatically creates all necessary tables when you establish the connection
</p>
</div>

</div>

</div>

#### PostgreSQL Setup with Docker

<div style="background: white; border: 2px solid #667eea; border-radius: 10px; padding: 2em; margin: 2em 0; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">

```bash
# Create PostgreSQL container
docker run -d \
  --name postgres-automation \
  -e POSTGRES_DB=automation_db \
  -e POSTGRES_USER=automation_user \
  -e POSTGRES_PASSWORD=your_password \
  -p 5432:5432 \
  -v postgres_data:/var/lib/postgresql/data \
  postgres:15

# Wait for PostgreSQL to be ready, then connect PyAutomation
```

</div>

#### MySQL Setup with Docker

<div style="background: white; border: 2px solid #667eea; border-radius: 10px; padding: 2em; margin: 2em 0; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">

```bash
# Create MySQL container
docker run -d \
  --name mysql-automation \
  -e MYSQL_DATABASE=automation_db \
  -e MYSQL_USER=automation_user \
  -e MYSQL_PASSWORD=your_password \
  -e MYSQL_ROOT_PASSWORD=root_password \
  -p 3306:3306 \
  -v mysql_data:/var/lib/mysql \
  mysql:8.0

# Wait for MySQL to be ready, then connect PyAutomation
```

</div>

!!! warning "Database Must Be Created Before Connection"
    **You must create and configure the database server/instance before attempting to connect through the web configuration interface.**
    
    - The database server must be running and accessible
    - The database instance must exist (for PostgreSQL/MySQL)
    - Connection credentials (host, port, user, password, database name) must be available
    - PyAutomation will automatically create all required tables when you establish the connection
    
    If you try to connect before the database is ready, you will encounter connection errors in the web interface.

---

## 🏃 Running the Application

### Development Mode

<div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #2196f3;">

<h3 style="color: #1976d2; font-size: 1.8em; margin-bottom: 1em;">
  💻 Development Setup
</h3>

<p style="font-size: 1.1em; color: #1565c0; margin-bottom: 1.5em;">
  To run the application locally for development:
</p>

```bash
python wsgi.py
```

<p style="font-size: 1em; color: #1565c0; margin-top: 1em;">
  Or simply:
</p>

```bash
./docker-entrypoint.sh
```

<p style="font-size: 1.1em; color: #1565c0; margin-top: 1.5em; font-weight: 600;">
  The application will start and be accessible at <code style="background: rgba(33, 150, 243, 0.2); padding: 0.2em 0.4em; border-radius: 4px;">http://localhost:8050</code>
</p>

</div>

!!! note "Database Connection Process"
    When you connect PyAutomation to a database through the web interface:
    
    1. **PyAutomation establishes the connection** to your pre-configured database server
    2. **Tables are created automatically** - PyAutomation will create all necessary tables if they don't exist
    3. **Default data is initialized** - Roles, variables, units, and data types are set up automatically
    4. **System is ready to use** - You can now configure tags, alarms, and other components
    
    **No manual table creation is required** - PyAutomation handles all schema initialization automatically upon connection.

---

### 🐳 Production (Docker)

<div style="background: linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #9c27b0;">

<h3 style="color: #7b1fa2; font-size: 1.8em; margin-bottom: 1em;">
  🚀 Production Deployment
</h3>

<p style="font-size: 1.1em; color: #6a1b9a; margin-bottom: 1.5em;">
  For production deployments, <strong>Docker is the recommended approach</strong> for reliability, scalability, and ease of management.
</p>

</div>

#### Docker Compose Configuration

Create a `docker-compose.yml` file in your project root with the following configuration:

```yaml
services:
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

<div style="background: #e8f5e9; border-left: 5px solid #4caf50; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<h4 style="color: #2e7d32; font-size: 1.3em; margin-bottom: 0.5em;">
  📝 Configuration Notes
</h4>

<ul style="color: #1b5e20; line-height: 1.8;">
  <li><strong>Image:</strong> Uses the official <code>knowai/automation</code> image. Set <code>AUTOMATION_VERSION</code> environment variable to pin a specific version (defaults to <code>latest</code>).</li>
  <li><strong>Ports:</strong> Web interface port (default <code>8050</code>). Override with <code>AUTOMATION_PORT</code> environment variable.</li>
  <li><strong>Volumes:</strong> Persistent storage for database (<code>automation_db</code>) and logs (<code>automation_logs</code>) to survive container restarts.</li>
  <li><strong>Logging:</strong> JSON file driver with rotation (10MB per file, max 3 files).</li>
  <li><strong>Resources:</strong> CPU and memory limits for production stability.</li>
  <li><strong>Healthcheck:</strong> Automatic health monitoring every 15 seconds.</li>
</ul>

</div>

#### Environment Variables for Production

<div style="background: white; border: 2px solid #667eea; border-radius: 10px; padding: 2em; margin: 2em 0; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">

<p style="font-size: 1.1em; color: #2d3748; margin-bottom: 1em;">
  For production deployments, you can create a <code>.env</code> file in the same directory as <code>docker-compose.yml</code> to customize the Docker Compose template without modifying the <code>docker-compose.yml</code> file itself.
</p>

<p style="margin: 1.5em 0 0.5em 0; font-weight: 700; color: #0f172a; font-size: 1.1em;">Example `.env` file for production:</p>

```ini
# Web Server Configuration  
AUTOMATION_PORT=8050                  # default 8050         
AUTOMATION_VERSION=2.0.0             # default latest
AUTOMATION_OPCUA_SERVER_PORT=53530    # default 53530
AUTOMATION_HMI_PORT=5000
AUTOMATION_APP_SECRET_KEY="12DFW7HJHJWER6W73338343-FEDF94-EF9EF-EFR9ER"
AUTOMATION_SUPERUSER_PASSWORD="super_ultra_secret_password"
AUTOMATION_DB_TYPE=postgresql
AUTOMATION_DB_HOST=xxx.xxx.xxx.xxx
AUTOMATION_DB_PORT=5432
AUTOMATION_DB_USER=xxxxxxxx
AUTOMATION_DB_PASSWORD=xxxxxxxxx
AUTOMATION_DB_NAME=xxxxxxx
```

<div style="background: rgba(102, 126, 234, 0.1); border-left: 4px solid #667eea; padding: 1em; margin-top: 1.5em; border-radius: 4px;">

<p style="margin: 0; color: #4a5568;">
  <strong>💡 Best Practices:</strong>
</p>

<ul style="color: #4a5568; margin-top: 0.5em;">
  <li><strong>Never commit <code>.env</code> files</strong> to version control if they contain sensitive information</li>
  <li>Use different <code>.env</code> files for different environments (<code>.env.production</code>, <code>.env.staging</code>)</li>
  <li>Document required variables in your deployment guide</li>
  <li>Use <code>.env.example</code> as a template that can be safely committed to version control</li>
</ul>

</div>

</div>

#### Running with Docker Compose

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5em; margin: 2em 0;">

<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; padding: 1.5em; color: white; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);">
<h4 style="color: white; font-size: 1.2em; margin-bottom: 0.5em;">1️⃣ Start</h4>
<p style="margin: 0; opacity: 0.9;">Start the container</p>
<code style="background: rgba(255,255,255,0.2); color: white; padding: 0.3em 0.6em; border-radius: 4px; display: block; margin-top: 0.5em;">docker compose --env-file .env up -d</code>
</div>

<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; padding: 1.5em; color: white; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);">
<h4 style="color: white; font-size: 1.2em; margin-bottom: 0.5em;">2️⃣ Logs</h4>
<p style="margin: 0; opacity: 0.9;">View logs</p>
<code style="background: rgba(255,255,255,0.2); color: white; padding: 0.3em 0.6em; border-radius: 4px; display: block; margin-top: 0.5em;">docker compose logs -f Automation</code>
</div>



<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; padding: 1.5em; color: white; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);">
<h4 style="color: white; font-size: 1.2em; margin-bottom: 0.5em;">3️⃣ Stop</h4>
<p style="margin: 0; opacity: 0.9;">Stop the container</p>
<code style="background: rgba(255,255,255,0.2); color: white; padding: 0.3em 0.6em; border-radius: 4px; display: block; margin-top: 0.5em;">docker compose down</code>
</div>

<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; padding: 1.5em; color: white; box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);">
<h4 style="color: white; font-size: 1.2em; margin-bottom: 0.5em;">4️⃣ Backend Logs</h4>
<p style="margin: 0; opacity: 0.9;">Detailed Backend Logs</p>
<code style="background: rgba(255,255,255,0.2); color: white; padding: 0.3em 0.6em; border-radius: 4px; display: block; margin-top: 0.5em;">docker exec -it Automation tail -n 100 /var/log/supervisor/backend.out.log</code>
</div>

</div>

!!! note "Database Setup for Docker Deployment"
    **For Docker deployments, ensure your database server is running before starting PyAutomation:**
    
    - **SQLite**: No additional setup needed - database file is created automatically in the volume
    - **PostgreSQL/MySQL**: You must have a database server running (either in a separate container or external)
    
    **Example docker-compose.yml with PostgreSQL:**
    
    ```yaml
    services:
      postgres:
        image: postgres:15
        container_name: "PostgreSQL"
        environment:
          POSTGRES_DB: automation_db
          POSTGRES_USER: automation_user
          POSTGRES_PASSWORD: your_password
        volumes:
          - postgres_data:/var/lib/postgresql/data
        ports:
          - "5432:5432"
    
      automation:
        # ... your automation service configuration ...
        depends_on:
          - postgres
        environment:
          # Database connection will be configured through web interface
          # or via API after containers are running
    ```
    
    **Connection Process:**
    1. Start the database container: `docker compose up -d postgres`
    2. Wait for database to be ready
    3. Start PyAutomation: `docker compose up -d automation`
    4. Connect to PyAutomation web interface and configure database connection
    5. PyAutomation will automatically create all tables upon successful connection

---

## ✅ Verify Installation

<div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #4caf50;">

<h3 style="color: #2e7d32; font-size: 1.8em; margin-bottom: 1em;">
  🎉 Installation Complete!
</h3>

<p style="font-size: 1.1em; color: #1b5e20; margin-bottom: 1.5em;">
  Once running, navigate to the following endpoints to verify your installation:
</p>

<div style="background: white; border-radius: 8px; padding: 1.5em; margin-top: 1em; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">

<p style="margin: 0; color: #2d3748;">
  <strong>API Documentation:</strong> <code style="background: rgba(76, 175, 80, 0.1); padding: 0.2em 0.4em; border-radius: 4px;">http://localhost:8050/api/docs</code>
</p>

<p style="margin: 0.5em 0 0 0; color: #2d3748;">
  <strong>Config Wbesite:</strong> <code style="background: rgba(76, 175, 80, 0.1); padding: 0.2em 0.4em; border-radius: 4px;">http://localhost:{AUTOMATION_HMI_PORT}/hmi</code>
</p>

<p style="margin: 0.5em 0 0 0; color: #2d3748;">
  <strong>Health Check:</strong> <code style="background: rgba(76, 175, 80, 0.1); padding: 0.2em 0.4em; border-radius: 4px;">http://localhost:8050/api/healthcheck/</code>
</p>

</div>

<p style="font-size: 1em; color: #1b5e20; margin-top: 1.5em;">
  You should see a JSON response indicating the service is healthy. ✅
</p>

</div>

---

## 🎯 Next Steps: Complete Configuration

<div align="center" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 15px; padding: 3em 2em; margin: 3em 0; box-shadow: 0 15px 35px rgba(0,0,0,0.2);">

<h2 style="color: white; font-size: 2em; margin-bottom: 1.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">
  Ready to Configure PyAutomation?
</h2>

<p style="color: white; font-size: 1.3em; line-height: 1.8; margin-bottom: 2em; opacity: 0.95;">
  After successfully installing and starting PyAutomation, you need to configure the system to make it fully operational. The following configuration steps are essential:
</p>

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1.5em;">

<div style="background: white; border-radius: 10px; padding: 1.5em; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
<h4 style="color: #667eea; font-size: 1.2em; margin-bottom: 0.5em;">💾 Database</h4>
<p style="color: #4a5568; margin: 0;">Set up database connections for data persistence</p>
</div>

<div style="background: white; border-radius: 10px; padding: 1.5em; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
<h4 style="color: #667eea; font-size: 1.2em; margin-bottom: 0.5em;">🏷️ Tags</h4>
<p style="color: #4a5568; margin: 0;">Create and configure process variables</p>
</div>

<div style="background: white; border-radius: 10px; padding: 1.5em; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
<h4 style="color: #667eea; font-size: 1.2em; margin-bottom: 0.5em;">🔌 Communications</h4>
<p style="color: #4a5568; margin: 0;">Configure OPC UA servers and clients</p>
</div>

<div style="background: white; border-radius: 10px; padding: 1.5em; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
<h4 style="color: #667eea; font-size: 1.2em; margin-bottom: 0.5em;">🚨 Alarms</h4>
<p style="color: #4a5568; margin: 0;">Define alarm conditions and thresholds</p>
</div>

</div>

<div style="margin-top: 2em;">

<a href="Users_Guide/index.md" style="display: inline-block; background: white; color: #667eea; padding: 1em 2em; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 1.1em; box-shadow: 0 4px 6px rgba(0,0,0,0.2); transition: transform 0.2s;">
  📖 Explore User Guide →
</a>

</div>

</div>

For detailed step-by-step instructions on completing these configurations, please refer to the **[User Guide](Users_Guide/index.md)**. The User Guide provides comprehensive documentation on:

- **[Database Configuration](Users_Guide/Database/index.md)**: Connecting to SQLite, PostgreSQL, or MySQL databases
- **[Tags Management](Users_Guide/Tags/index.md)**: Creating, updating, and managing process tags
- **[OPC UA Communications](Users_Guide/Communications/index.md)**: Setting up OPC UA server and client connections
- **[Alarms Setup](Users_Guide/Alarms/index.md)**: Configuring alarm conditions, thresholds, and states

Follow the User Guide modules in sequence to ensure a complete and properly configured PyAutomation deployment.
