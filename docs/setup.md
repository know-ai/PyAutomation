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
PORT=8050
WORKERS=1
THREADS=10

# OPC UA Server Configuration
OPCUA_SERVER_PORT=53530

# Logging Configuration
LOG_MAX_BYTES=10485760  # 10 MB
LOG_BACKUP_COUNT=5
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

1.  Build the image (optional, or use the pre-built one):

    ```bash
    docker build -t pyautomation .
    ```

2.  Run with Docker Compose:
    Ensure you have a `docker-compose.yml` configured (see README.md for an example) and run:
    ```bash
    docker-compose up -d
    ```

## Verify Installation

Once running, navigate to `http://localhost:8050/api/docs` (if API docs are enabled) or check the health endpoint:
`http://localhost:8050/api/healthcheck/` (Assuming standard routes are set up).

You should see a JSON response indicating the service is healthy.
