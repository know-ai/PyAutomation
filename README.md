# PyAutomation

The development intention of this framework is to provide the ability to develop industrial applications where processes need to be executed concurrently and field data need to be managed for monitoring, control, and supervision applications.

![Core](docs/img/PyAutomationCore.svg)

In the image above, you can generally see the architecture and interaction of the different modules that make up the framework.

For this, state machines are available that run in the background and concurrently to acquire data by query (DAQ), Acquire Data by Exception (DAS) and any other general purpose state machine.

It has a memory persistence module for real-time variables that we call (CVT, Current Value Table).

There is also an alarm management system

And finally, the disk persistence of the variables to provide functionalities for historical trends of the field variables.

# Run Config Page

## Crearte Virtual Environment

```python
python3 -m venv venv
. venv/bin/activate
```

## Install Dependencies

```python
pip install --upgrade pip
pip install -r requirements.txt
```

## Run Config page

```python

./docker-entrypoint.sh
```

# Deploy

Make the following `.env` file:

```
AUTOMATION_PORT=8050
AUTOMATION_VERSION=1.1.3
AUTOMATION_OPCUA_SERVER_PORT=53530
AUTOMATION_LOG_MAX_BYTES=5000  # 10MB en bytes
AUTOMATION_LOG_BACKUP_COUNT=3
```

## Docker

If you want to deploy it using docker compose, make the following `docker-compose.yml` file:

```YaMl
services:
  automation:
    container_name: "Automation"
    image: "knowai/automation:${AUTOMATION_VERSION}"
    restart: always
    ports:
      - ${AUTOMATION_PORT}:${AUTOMATION_PORT}
    volumes:
      - automation_db:/app/db
      - automation_logs:/app/logs
    logging:
      driver: "json-file"
      options:
        max-size: "10m" # Rota cuando llega a 10MB
        max-file: "3" # Guarda máximo 3 archivos (30MB total)
    environment:
      OPCUA_SERVER_PORT: ${AUTOMATION_OPCUA_SERVER_PORT}
      LOG_MAX_BYTES: ${AUTOMATION_LOG_MAX_BYTES}
      LOG_BACKUP_COUNT: ${AUTOMATION_LOG_BACKUP_COUNT}
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

Start the docker compose file

```
sudo docker-compose --env-file .env up -d
```

Go to http://host:${AUTOMATION_PORT} to view the config page
