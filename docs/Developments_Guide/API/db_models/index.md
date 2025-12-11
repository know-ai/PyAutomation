# Database Models API

This section documents the database models used for data persistence in PyAutomation. These models are built using `peewee` ORM and define the schema for SQLite, PostgreSQL, or MySQL databases.

## Entity-Relationship Diagram

The following diagram shows the relationships between all database tables in PyAutomation:

```mermaid
erDiagram
    Manufacturer ||--o{ Segment : "has"
    Segment ||--o{ Tags : "contains"
    Variables ||--o{ Units : "has"
    Units ||--o{ Tags : "uses"
    Units ||--o{ TagValue : "measures"
    DataTypes ||--o{ Tags : "defines"
    Tags ||--o{ TagValue : "stores"
    Tags ||--o{ Alarms : "monitors"
    Tags }o--o{ TagsMachines : "linked"
    Machines }o--o{ TagsMachines : "linked"
    AlarmTypes ||--o{ Alarms : "defines"
    AlarmStates ||--o{ Alarms : "has"
    AlarmStates ||--o{ AlarmSummary : "tracks"
    Alarms ||--o{ AlarmSummary : "generates"
    Roles ||--o{ Users : "assigns"
    Users ||--o{ Events : "creates"
    Users ||--o{ Logs : "generates"
    AlarmSummary ||--o| Logs : "references"
    Events ||--o| Logs : "references"
    AccessType ||--o{ OPCUAServer : "defines"

    Manufacturer {
        int id PK
        string name UK
    }
    
    Segment {
        int id PK
        string name
        int manufacturer_id FK
    }
    
    Variables {
        int id PK
        string name UK
    }
    
    Units {
        int id PK
        string name UK
        string unit UK
        int variable_id FK
    }
    
    DataTypes {
        int id PK
        string name UK
    }
    
    Tags {
        int id PK
        string identifier UK
        string name UK
        string display_name UK
        int unit_id FK
        int data_type_id FK
        int segment_id FK "nullable"
        int display_unit_id FK
        string description
        string opcua_address
        string node_namespace
        int scan_time
        float dead_band
        boolean active
        boolean process_filter
        boolean gaussian_filter
        float gaussian_filter_threshold
        float gaussian_filter_r_value
        boolean out_of_range_detection
        boolean outlier_detection
        boolean frozen_data_detection
    }
    
    TagValue {
        int id PK
        int tag_id FK
        int unit_id FK
        float value
        datetime timestamp
    }
    
    AlarmTypes {
        int id PK
        string name UK
    }
    
    AlarmStates {
        int id PK
        string name UK
        string mnemonic
        string condition
        string status
    }
    
    Alarms {
        int id PK
        string identifier UK
        string name UK
        int tag_id FK
        int trigger_type_id FK
        float trigger_value
        string description
        int state_id FK
        datetime timestamp
    }
    
    AlarmSummary {
        int id PK
        int alarm_id FK
        int state_id FK
        datetime alarm_time
        datetime ack_time
    }
    
    Roles {
        int id PK
        string identifier UK
        string name UK
        int level
    }
    
    Users {
        int id PK
        string identifier UK
        string username UK
        string email UK
        int role_id FK
        string password
        string token
        string name
        string lastname
    }
    
    Events {
        int id PK
        datetime timestamp
        string message
        string description
        string classification
        int priority
        int criticity
        int user_id FK
    }
    
    Logs {
        int id PK
        datetime timestamp
        string message
        string description
        string classification
        int user_id FK
        int alarm_summary_id FK "nullable"
        int event_id FK "nullable"
    }
    
    Machines {
        int id PK
        string identifier UK
        string name UK
        float interval
        float threshold
        int on_delay
        string description
        string classification
        int buffer_size
        string buffer_roll_type
        int criticity
        int priority
    }
    
    TagsMachines {
        int id PK
        int tag_id FK
        int machine_id FK
        string default_tag_name
    }
    
    OPCUA {
        int id PK
        string client_name UK
        string host
        int port
    }
    
    AccessType {
        int id PK
        string name UK
    }
    
    OPCUAServer {
        int id PK
        string name UK
        string namespace UK
        int access_type_id FK "nullable"
    }
```

## Models

- **[Core Models](core.md)**: Base classes and common utilities.
- **[Alarms Models](alarms.md)**: Models for alarm definitions and history.
- **[Tags Models](tags.md)**: Models for tag configuration and values.
- **[Users Models](users.md)**: Models for user authentication and roles.
- **[Events Models](events.md)**: Models for system event logging.
- **[Logs Models](logs.md)**: Models for application logs.
- **[Machines Models](machines.md)**: Models for state machine persistence.
- **[OPC UA Models](opcua.md)**: Models for OPC UA client and server configuration.
