# PyAutomation

[![Documentation Status](https://readthedocs.org/projects/pyautomation/badge/?version=latest)](https://pyautomation.readthedocs.io/en/latest/?badge=latest)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/release/python-3100/)

**PyAutomation** is a robust, concurrent framework designed for developing industrial automation applications using Python. It bridges the gap between industrial protocols (like OPC UA) and modern software development capabilities, enabling Data Science, AI, and web-based SCADA applications.

![Core Architecture](docs/img/PyAutomationCore.svg)

## Features

- **Concurrency & State Machines**: Built-in support for running multiple state machines concurrently for complex process control and monitoring.
- **Industrial Connectivity**: Native support for OPC UA (Client & Server) to communicate with PLCs, RTUs, and other industrial devices.
- **Data Acquisition**:
  - **DAQ (Data Acquisition)**: Polling-based data collection.
  - **DAS (Data Acquisition by Subscription)**: Event-driven data collection for efficiency.
- **CVT (Current Value Table)**: In-memory real-time database for fast access to process variables.
- **Data Persistence**:
  - **Historian**: Log historical data to SQL databases (SQLite, PostgreSQL, MySQL).
  - **Alarms & Events**: Comprehensive alarm management and event logging system compliant with ISA 18.2 concepts.
- **Web Integration**: Integrated Dash/Flask web server with Socket.IO for real-time HMI/SCADA interfaces.
- **Extensible**: Easy to extend with custom state machines and logic.

## Installation

### Prerequisites

- Python 3.10 or higher
- pip
- virtualenv (recommended)

### Local Setup

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/know-ai/PyAutomation.git
    cd PyAutomation
    ```

2.  **Create a virtual environment:**

    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**

    ```bash
    pip install --upgrade pip
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    ./docker-entrypoint.sh
    # Or directly with python:
    # python wsgi.py
    ```

## Docker Deployment

PyAutomation is container-ready. You can deploy it easily using Docker Compose.

1.  **Create an `.env` file:**

    ```ini
    AUTOMATION_PORT=8050
    AUTOMATION_VERSION=1.1.3
    AUTOMATION_OPCUA_SERVER_PORT=53530
    AUTOMATION_LOG_MAX_BYTES=5242880  # 5MB
    AUTOMATION_LOG_BACKUP_COUNT=3
    ```

2.  **Create a `docker-compose.yml`:**

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

3.  **Start the service:**

    ```bash
    docker-compose --env-file .env up -d
    ```

4.  **Access the Dashboard:**
    Go to `http://localhost:8050` (or your configured port).

## Documentation

Full documentation is available at [Read the Docs](https://pyautomation.readthedocs.io/).

It covers:

- **Architecture**: detailed system design.
- **User Guide**: how to use the alarms, tags, and database features.
- **Developer Guide**: API reference and how to build custom state machines.

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to submit pull requests, report issues, and the code of conduct.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
