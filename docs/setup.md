# Installation and Setup

This guide covers the installation and configuration of PyAutomation for both development and production environments.

## Prerequisites

Before installing PyAutomation, ensure you have the following installed:

- **Python**: Version 3.10 or higher.
- **pip**: Python package installer.
- **Virtualenv**: (Optional but recommended) for creating isolated Python environments.
- **Git**: For version control and cloning the repository.

## Installation Steps

### 1. Clone the Repository

Start by cloning the PyAutomation repository to your local machine:

```bash
git clone https://github.com/know-ai/PyAutomation.git
cd PyAutomation
```

### 2. Set Up a Virtual Environment

It is best practice to run Python applications in a virtual environment to avoid dependency conflicts.

**On Linux/macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**

```powershell
python -m venv venv
.\venv\Scripts\activate
```

### 3. Install Dependencies

Install the required Python packages using `pip`:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

If you are developing documentation or running tests, you might also want to install additional requirements:

```bash
pip install -r docs_requirements.txt
```

## Configuration

PyAutomation uses environment variables and configuration files to manage settings.

### Environment Variables

Create a `.env` file in the root directory (or set these variables in your environment) to configure the application.

Example `.env`:

```ini
# Web Server Configuration  
AUTOMATION_PORT=8050                  # default 8050         
AUTOMATION_VERSION=1.1.10             # default latest
AUTOMATION_OPCUA_SERVER_PORT=53530    # default 53530
AUTOMATION_APP_SECRET_KEY="12DFW7HJHJWER6W73338343-FEDF94-EF9EF-EFR9ER" # default "073821603fcc483f9afee3f1500782a4"
AUTOMATION_SUPERUSER_PASSWORD="super_ultra_secret_password"
```

### Database Configuration

By default, PyAutomation uses SQLite for development (`db/app.db`). For production, you can configure PostgreSQL or MySQL via the `db_config.json` or through the application's API configuration methods.

## Running the Application

### Development Mode

To run the application locally for development:

```bash
python wsgi.py
```

Or simply:

```bash
./docker-entrypoint.sh
```

The application will start and be accessible at `http://localhost:8050`.

### Production (Docker)

For production deployments, Docker is the recommended approach.

#### Docker Compose Configuration

Create a `docker-compose.yml` file in your project root with the following configuration:

```yaml
services:
  automation:
    container_name: "Automation"
    image: "knowai/automation:${AUTOMATION_VERSION:-latest}"
    restart: always
    ports:
      - ${AUTOMATION_PORT:-8050}:${AUTOMATION_PORT:-8050}
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

**Configuration Notes:**

- **Image**: Uses the official `knowai/automation` image. Set `AUTOMATION_VERSION` environment variable to pin a specific version (defaults to `latest`).
- **Ports**: Web interface port (default `8050`). Override with `AUTOMATION_PORT` environment variable.
- **Volumes**: Persistent storage for database (`automation_db`) and logs (`automation_logs`) to survive container restarts.
- **Logging**: JSON file driver with rotation (10MB per file, max 3 files).
- **Resources**: CPU and memory limits for production stability.
- **Healthcheck**: Automatic health monitoring every 15 seconds.

#### Environment Variables for Production

For production deployments, you can create a `.env` file in the same directory as `docker-compose.yml` to customize the Docker Compose template without modifying the `docker-compose.yml` file itself. This approach allows you to:

- Keep the `docker-compose.yml` template unchanged
- Use different configurations for different environments (dev, staging, production)
- Override default values easily
- Maintain version control without exposing sensitive values

**Example `.env` file for production:**

```ini
# Web Server Configuration  
AUTOMATION_PORT=8050                  # default 8050         
AUTOMATION_VERSION=1.1.10             # default latest
AUTOMATION_OPCUA_SERVER_PORT=53530    # default 53530
AUTOMATION_APP_SECRET_KEY="12DFW7HJHJWER6W73338343-FEDF94-EF9EF-EFR9ER" # default "073821603fcc483f9afee3f1500782a4"
AUTOMATION_SUPERUSER_PASSWORD="super_ultra_secret_password"
```

**How it works:**

Docker Compose automatically reads the `.env` file from the same directory when you run `docker-compose up`. The variables defined in `.env` will replace the placeholders in `docker-compose.yml` (e.g., `${AUTOMATION_PORT:-8050}` will use the value from `.env` if present, or default to `8050` if not).

**Best Practices:**

- **Never commit `.env` files** to version control if they contain sensitive information
- Use different `.env` files for different environments (`.env.production`, `.env.staging`)
- Document required variables in your deployment guide
- Use `.env.example` as a template that can be safely committed to version control

#### Running with Docker Compose

1. **Build the image** (optional, or use the pre-built one):

    ```bash
    docker build -t pyautomation .
    ```

2. **Start the container**:

    ```bash
    docker-compose up -d
    ```

3. **View logs**:

    ```bash
    docker-compose logs -f automation
    ```

4. **Stop the container**:

    ```bash
    docker-compose down
    ```

5. **Restart the container**:

    ```bash
    docker-compose restart
    ```

## Verify Installation

Once running, navigate to `http://localhost:8050/api/docs` (if API docs are enabled) or check the health endpoint:
`http://localhost:8050/api/healthcheck/` (Assuming standard routes are set up).

You should see a JSON response indicating the service is healthy.

## Next Steps: Complete Configuration

After successfully installing and starting PyAutomation, you need to configure the system to make it fully operational. The following configuration steps are essential:

1. **Database Configuration**: Set up database connections for data persistence and historical logging
2. **Tags Configuration**: Create and configure process variables (tags) that represent your industrial data points
3. **Communications Setup**: Configure OPC UA servers and clients for field device connectivity
4. **Alarms Configuration**: Define alarm conditions and thresholds for process monitoring and safety

For detailed step-by-step instructions on completing these configurations, please refer to the **[User Guide](Users_Guide/index.md)**. The User Guide provides comprehensive documentation on:

- [Database Configuration](Users_Guide/Database/index.md): Connecting to SQLite, PostgreSQL, or MySQL databases
- [Tags Management](Users_Guide/Tags/index.md): Creating, updating, and managing process tags
- [OPC UA Communications](Users_Guide/Communications/index.md): Setting up OPC UA server and client connections
- [Alarms Setup](Users_Guide/Alarms/index.md): Configuring alarm conditions, thresholds, and states

Follow the User Guide modules in sequence to ensure a complete and properly configured PyAutomation deployment.
