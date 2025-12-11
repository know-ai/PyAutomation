# Settings API

REST API endpoints for application settings and configuration management.

## Configuration Export/Import

### GET `/api/settings/export_config`

Exports all configuration data to a JSON file. Excludes historical data (TagValue, Events, Logs, AlarmSummary).

**Headers:**
- `X-API-KEY`: Authentication token (required)

**Response (200):**
- Content-Type: `application/json`
- Content-Disposition: `attachment; filename=configuration_export.json`
- Body: JSON file with all configuration data

**Response (400):**
```json
{
  "message": "Database not connected"
}
```

**Response (401):**
```json
{
  "message": "Token is missing or invalid"
}
```

**Example:**
```bash
curl -X GET \
  http://localhost:5000/api/settings/export_config \
  -H "X-API-KEY: your_token" \
  -o configuration_export.json
```

**Exported Data Structure:**
```json
{
  "version": "1.0",
  "exported_at": "2024-01-15T10:30:00+00:00",
  "data": {
    "Manufacturer": [...],
    "Segment": [...],
    "Variables": [...],
    "Units": [...],
    "DataTypes": [...],
    "Tags": [...],
    "AlarmTypes": [...],
    "AlarmStates": [...],
    "Alarms": [...],
    "Roles": [...],
    "Users": [...],
    "OPCUA": [...],
    "AccessType": [...],
    "OPCUAServer": [...],
    "Machines": [...],
    "TagsMachines": [...]
  }
}
```

### POST `/api/settings/import_config`

Imports configuration data from a JSON file. Restores all configuration tables while preserving historical data.

**Headers:**
- `X-API-KEY`: Authentication token (required)

**Request:**
- Content-Type: `multipart/form-data`
- `file`: JSON configuration file (required)

**Response (200):**
```json
{
  "message": "Configuration imported: 150 records imported, 10 skipped, 0 errors",
  "summary": {
    "imported": 150,
    "skipped": 10,
    "errors": 0
  },
  "results": {
    "imported": {
      "Variables": 5,
      "Units": 12,
      "Tags": 50,
      "Alarms": 20,
      "Roles": 3,
      "Users": 5,
      ...
    },
    "skipped": {
      "Users": 2,
      "Roles": 1,
      ...
    },
    "errors": {
      "Tags": ["tag_name: Unit not found"],
      ...
    }
  }
}
```

**Response (400):**
```json
{
  "message": "No file provided"
}
```

or

```json
{
  "message": "Invalid JSON file: Expecting value: line 1 column 1 (char 0)"
}
```

**Response (401):**
```json
{
  "message": "Token is missing or invalid"
}
```

**Example:**
```bash
curl -X POST \
  http://localhost:5000/api/settings/import_config \
  -H "X-API-KEY: your_token" \
  -F "file=@configuration_export.json"
```

**Import Order:**
The import process follows a specific order to respect foreign key dependencies:

1. Variables (no dependencies)
2. Units (depends on Variables)
3. DataTypes (no dependencies)
4. Manufacturer (no dependencies)
5. Segment (depends on Manufacturer)
6. Tags (depends on Units, DataTypes, Segment)
7. AlarmTypes (no dependencies)
8. AlarmStates (no dependencies)
9. Alarms (depends on Tags, AlarmTypes, AlarmStates)
10. Roles (no dependencies)
11. Users (depends on Roles)
12. OPCUA (no dependencies)
13. AccessType (no dependencies)
14. OPCUAServer (depends on AccessType)
15. Machines (no dependencies)
16. TagsMachines (depends on Tags and Machines)

**Notes:**
- Duplicate records (based on unique names) are skipped during import
- Historical data (TagValue, Events, Logs, AlarmSummary) is not affected
- User passwords are set to default values and should be reset after import

## Application Settings

### PUT `/api/settings/update`

Updates various application settings.

**Headers:**
- `X-API-KEY`: Authentication token (required)

**Request Body:**
```json
{
  "logger_period": 1.0,
  "log_max_bytes": 10485760,
  "log_backup_count": 3,
  "log_level": 20
}
```

**Parameters:**
- `logger_period` (float, optional): Logger worker period in seconds (>= 1.0)
- `log_max_bytes` (int, optional): Max bytes for log file rotation (>= 1024). Must be provided together with `log_backup_count`
- `log_backup_count` (int, optional): Number of backup log files to keep (>= 1). Must be provided together with `log_max_bytes`
- `log_level` (int, optional): Logging level (0=NOTSET, 10=DEBUG, 20=INFO, 30=WARNING, 40=ERROR, 50=CRITICAL)

**Response (200):**
```
Settings updated
```

**Response (400):**
```
Logger period must be >= 1.0
```

or

```
Both log_max_bytes and log_backup_count must be provided together
```

**Response (401):**
```json
{
  "message": "Token is missing or invalid"
}
```

### PUT `/api/settings/logger_period`

Updates only the logger worker period.

**Headers:**
- `X-API-KEY`: Authentication token (required)

**Request Body:**
```json
{
  "logger_period": 2.0
}
```

**Parameters:**
- `logger_period` (float, required): Logger worker period in seconds (>= 1.0)

**Response (200):**
```
Logger period updated
```

**Response (400):**
```
Logger period must be >= 1.0
```

**Response (401):**
```json
{
  "message": "Token is missing or invalid"
}
```

