# Architecture Components: Workers, Engines, and Managers

<div align="center" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; padding: 3em 2em; margin: 2em 0; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">

<h2 style="color: white; font-size: 2.5em; margin-bottom: 0.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); font-weight: 700;">
  🏗️ Core Architectural Components
</h2>

<p style="color: white; font-size: 1.4em; margin-top: 1em; font-weight: 500; opacity: 0.95;">
  This document provides a technical explanation of the three fundamental architectural components in PyAutomation: <strong>Workers</strong>, <strong>Engines</strong>, and <strong>Managers</strong>. Understanding these components is crucial for developers working with or extending the framework.
</p>

</div>

## Overview

<div style="background: #f8f9fa; border-left: 5px solid #667eea; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 500;">
PyAutomation follows a <strong>layered architecture</strong> that separates concerns into three distinct component types, each solving specific problems in industrial automation systems:
</p>

</div>

```
┌─────────────────────────────────────────────────────────┐
│                    Managers                             │
│  (Orchestration & Business Logic Coordination)         │
└──────────────────┬──────────────────────────────────────┘
                   │ Uses
┌──────────────────▼──────────────────────────────────────┐
│                    Engines                              │
│  (Thread-Safe Data Access & Processing)                 │
└──────────────────┬──────────────────────────────────────┘
                   │ Used by
┌──────────────────▼──────────────────────────────────────┐
│                    Workers                              │
│  (Background Thread Execution)                         │
└─────────────────────────────────────────────────────────┘
```

---

## Managers - Orchestration Layer

<div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #2196f3;">

<h3 style="color: #0d47a1; font-size: 1.8em; margin-bottom: 1em; font-weight: 700;">
  🎯 High-Level Coordination & Business Logic
</h3>

### Purpose and Responsibility

<div style="background: #f8f9fa; border-left: 5px solid #2196f3; padding: 1.5em; margin: 1.5em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 500;">
<strong>Managers</strong> are <strong>orchestration components</strong> that coordinate business logic and manage the lifecycle of related resources. They act as <strong>facades</strong> that provide high-level APIs for complex operations involving multiple subsystems.
</p>

</div>

### Problems They Solve

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Resource Coordination</strong>: Managing collections of related objects (alarms, state machines, database connections)</li>
<li><strong>Business Logic</strong>: Implementing domain-specific rules and workflows</li>
<li><strong>Lifecycle Management</strong>: Creating, updating, deleting, and querying resources</li>
<li><strong>Cross-System Integration</strong>: Coordinating between CVT, database, and external systems</li>
</ol>

</div>

### Key Characteristics

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Singleton Pattern</strong>: One instance per application</li>
<li><strong>High-Level API</strong>: Provide convenient methods for common operations</li>
<li><strong>State Management</strong>: Maintain registries of managed resources</li>
<li><strong>Business Rules</strong>: Enforce validation and business logic</li>
</ul>

</div>

</div>

### Managers in PyAutomation

#### 1. **DBManager** (`automation/managers/db.py`)

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Responsibility:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>Central coordinator for all database operations</li>
<li>Manages database connection lifecycle</li>
<li>Initializes and coordinates multiple logging engines</li>
<li>Registers database models and handles table creation</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Key Operations:</strong>
</p>

```python
# Manages database connection
db_manager.set_db(database_instance)

# Coordinates multiple engines
db_manager.alarms_logger.query(...)
db_manager.events_logger.query(...)
db_manager.users_logger.query(...)
```

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0 0; font-weight: 500;">
<strong>Why a Manager?</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Single point of coordination for all database-related operations</li>
<li>Ensures consistent database configuration across all engines</li>
<li>Manages the relationship between CVT and database persistence</li>
</ul>

</div>

#### 2. **AlarmManager** (`automation/managers/alarms.py`)

<div style="background: #ffebee; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #f44336;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Responsibility:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>Manages the collection of all alarms in the system</li>
<li>Validates alarm configurations (duplicate checks, trigger value validation)</li>
<li>Coordinates between CVT (for tag values) and alarm state machines</li>
<li>Handles real-time communication via SocketIO</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Key Operations:</strong>
</p>

```python
# Create and register alarm
alarm_manager.append_alarm(name, tag, type, trigger_value)

# Retrieve alarm
alarm = alarm_manager.get_alarm_by_name(name)

# Update alarm state
alarm_manager.update_alarm(name, ...)
```

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0 0; font-weight: 500;">
<strong>Why a Manager?</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Central registry prevents duplicate alarms</li>
<li>Enforces business rules (e.g., one alarm type per tag)</li>
<li>Coordinates alarm lifecycle with CVT observers</li>
</ul>

</div>

#### 3. **StateMachineManager** (`automation/managers/state_machine.py`)

<div style="background: #f3e5f5; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #9c27b0;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Responsibility:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>Registry of all state machines in the system</li>
<li>Manages execution configuration (intervals, sync/async mode)</li>
<li>Provides serialization for API responses</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Key Operations:</strong>
</p>

```python
# Register state machine
state_machine_manager.append_machine(machine)

# Get all machines with configuration
machines = state_machine_manager.get_machines()  # Returns [(machine, interval, mode), ...]
```

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0 0; font-weight: 500;">
<strong>Why a Manager?</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Single source of truth for all state machines</li>
<li>Enables workers to discover and execute machines</li>
<li>Provides configuration management</li>
</ul>

</div>

#### 4. **OPCUAClientManager** (`automation/managers/opcua_client.py`)

<div style="background: #fff3e0; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #ff9800;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Responsibility:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>Manages multiple OPC UA client connections</li>
<li>Handles client lifecycle (connect, disconnect, reconnect)</li>
<li>Coordinates subscriptions and data flow to CVT</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Key Operations:</strong>
</p>

```python
# Add OPC UA client
opcua_client_manager.add_client(url, client_name)

# Subscribe tag to OPC UA node
opcua_client_manager.subscribe(tag, address, namespace)
```

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0 0; font-weight: 500;">
<strong>Why a Manager?</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Manages multiple concurrent OPC UA connections</li>
<li>Handles reconnection logic and connection pooling</li>
<li>Coordinates data flow from external systems to CVT</li>
</ul>

</div>

### Manager Pattern Benefits

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Single Responsibility</strong>: Each manager focuses on one domain (alarms, database, state machines)</li>
<li><strong>Encapsulation</strong>: Hides complexity of coordinating multiple engines</li>
<li><strong>Consistency</strong>: Ensures business rules are applied uniformly</li>
<li><strong>Testability</strong>: Managers can be mocked for testing dependent components</li>
</ul>

</div>

---

## Engines - Thread-Safe Processing Layer

<div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #4caf50;">

<h3 style="color: #1b5e20; font-size: 1.8em; margin-bottom: 1em; font-weight: 700;">
  🔒 Thread-Safe Data Access & Processing
</h3>

### Purpose and Responsibility

<div style="background: #f8f9fa; border-left: 5px solid #4caf50; padding: 1.5em; margin: 1.5em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 500;">
<strong>Engines</strong> are <strong>thread-safe wrappers</strong> that provide synchronized access to shared resources (primarily database operations). They solve the <strong>concurrency problem</strong> in multi-threaded industrial systems.
</p>

</div>

### Problems They Solve

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Thread Safety</strong>: Prevent race conditions when multiple threads access shared resources</li>
<li><strong>Database Concurrency</strong>: Ensure safe database operations from multiple threads</li>
<li><strong>Request-Response Pattern</strong>: Provide synchronous-like interface for asynchronous operations</li>
<li><strong>Resource Locking</strong>: Coordinate access to singleton resources</li>
</ol>

</div>

### Key Characteristics

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Singleton Pattern</strong>: One instance shared across all threads</li>
<li><strong>Thread-Safe</strong>: Uses locks to serialize access</li>
<li><strong>Request-Response</strong>: Queues requests and waits for responses</li>
<li><strong>Wrapper Pattern</strong>: Wraps a Logger (BaseLogger) that does actual work</li>
</ul>

</div>

</div>

### Engine Architecture

```python
BaseEngine (Thread-Safe Wrapper)
    │
    ├── Uses locks (request_lock, response_lock)
    ├── Implements request-response pattern
    └── Wraps → BaseLogger (Actual Implementation)
                    │
                    └── Does actual database operations
```

### Engines in PyAutomation

#### 1. **DataLoggerEngine** (`automation/logger/datalogger.py`)

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Responsibility:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>Thread-safe access to tag value logging operations</li>
<li>Provides methods for reading/writing historical tag data</li>
<li>Handles tabular data queries with pagination</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Thread Safety Mechanism:</strong>
</p>

```python
# Request
engine.request({"action": "read_tabular_data", "parameters": {...}})

# Response (waits for completion)
result = engine.response()  # Blocks until operation completes
```

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0 0; font-weight: 500;">
<strong>Why an Engine?</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Multiple threads (workers, API handlers) may query historical data simultaneously</li>
<li>Prevents database connection conflicts and race conditions</li>
<li>Ensures data consistency during concurrent reads/writes</li>
</ul>

</div>

#### 2. **AlarmsLoggerEngine** (`automation/logger/alarms.py`)

<div style="background: #ffebee; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #f44336;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Responsibility:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>Thread-safe access to alarm summary/history operations</li>
<li>Manages alarm state persistence</li>
<li>Provides paginated alarm history queries</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0 0; font-weight: 500;">
<strong>Why an Engine?</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Alarm state changes can occur from multiple threads (state machines, API, user actions)</li>
<li>Prevents concurrent modification of alarm records</li>
<li>Ensures alarm history is written atomically</li>
</ul>

</div>

#### 3. **CVTEngine** (`automation/tags/cvt.py`)

<div style="background: #e1f5fe; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #03a9f4;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Responsibility:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>Thread-safe access to the Current Value Table (CVT)</li>
<li>Manages tag creation, updates, and queries</li>
<li>Coordinates observer notifications</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Thread Safety:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>Uses thread-safe dictionaries and locks</li>
<li>Provides atomic tag updates</li>
<li>Ensures observers are notified correctly</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0 0; font-weight: 500;">
<strong>Why an Engine?</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>CVT is accessed by multiple threads simultaneously:
    <ul style="margin-top: 0.5em; margin-bottom: 0.5em;">
    <li>State machines reading tag values</li>
    <li>OPC UA clients writing values</li>
    <li>API handlers reading values</li>
    <li>Logger workers reading for persistence</li>
    </ul>
</li>
<li>Prevents data corruption and ensures consistency</li>
</ul>

</div>

#### 4. **EventsLoggerEngine**, **UsersLoggerEngine**, **LogsLoggerEngine**, etc.

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Responsibility:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Thread-safe access to their respective domain operations</li>
<li>Each follows the same pattern: Engine → Logger → Database</li>
</ul>

</div>

### Engine Pattern Benefits

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Thread Safety</strong>: Eliminates race conditions in multi-threaded environments</li>
<li><strong>Consistency</strong>: Ensures operations complete atomically</li>
<li><strong>Predictability</strong>: Request-response pattern makes async operations appear synchronous</li>
<li><strong>Resource Protection</strong>: Prevents concurrent access to shared resources (database, CVT)</li>
</ul>

</div>

### How Engines Work Internally

```python
class BaseEngine:
    def query(self, query_dict):
        # 1. Acquire request lock (only one request at a time)
        self._request_lock.acquire()
        
        # 2. Execute method on underlying logger
        method = getattr(self.logger, query["action"])
        result = method(**query["parameters"])
        
        # 3. Store response and release response lock
        self._response = {"result": True, "response": result}
        self._response_lock.release()
        
        # 4. Wait for response lock (blocks until operation completes)
        # 5. Return result and release request lock
```

**Key Insight**: The engine serializes all requests, ensuring only one database operation happens at a time, preventing conflicts.

---

## Workers - Background Execution Layer

<div style="background: linear-gradient(135deg, #fce4ec 0%, #f8bbd0 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #e91e63;">

<h3 style="color: #880e4f; font-size: 1.8em; margin-bottom: 1em; font-weight: 700;">
  ⚙️ Background Thread Execution
</h3>

### Purpose and Responsibility

<div style="background: #f8f9fa; border-left: 5px solid #e91e63; padding: 1.5em; margin: 1.5em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 500;">
<strong>Workers</strong> are <strong>background threads</strong> that execute periodic or continuous tasks. They run independently of the main application thread, enabling concurrent processing.
</p>

</div>

### Problems They Solve

<div style="background: #fce4ec; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #e91e63;">

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Non-Blocking Operations</strong>: Prevent long-running tasks from blocking the main thread</li>
<li><strong>Periodic Tasks</strong>: Execute tasks at regular intervals (data logging, health checks)</li>
<li><strong>Concurrent Execution</strong>: Run multiple state machines in parallel</li>
<li><strong>Resource Management</strong>: Handle background maintenance (database backups, reconnections)</li>
</ol>

</div>

### Key Characteristics

<div style="background: #fce4ec; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #e91e63;">

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Thread-Based</strong>: Extend <code>threading.Thread</code> or use <code>BaseWorker</code></li>
<li><strong>Lifecycle Management</strong>: Start, stop, and join operations</li>
<li><strong>Event-Driven</strong>: Use <code>threading.Event</code> for graceful shutdown</li>
<li><strong>Daemon Threads</strong>: Can be daemon threads that terminate with main process</li>
</ul>

</div>

</div>

### Workers in PyAutomation

#### 1. **LoggerWorker** (`automation/workers/logger.py`)

<div style="background: #fce4ec; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #e91e63;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Responsibility:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>Periodically writes tag values from CVT to database</li>
<li>Performs database maintenance (backups, vacuuming)</li>
<li>Monitors and reconnects OPC UA clients</li>
<li>Runs in background thread, independent of main application</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Execution Pattern:</strong>
</p>

```python
def run(self):
    while not self.stop_event.is_set():
        # 1. Get tags from queue
        tags_data = self.get_tags_from_queue(queue)
        
        # 2. Write to database via engine
        self.logger.query({"action": "write_tags", "parameters": {...}})
        
        # 3. Perform maintenance tasks
        self.sqlite_db_backup()
        self.check_opcua_connection()
        
        # 4. Sleep for period
        time.sleep(self._period)
```

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0 0; font-weight: 500;">
<strong>Why a Worker?</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Database writes should not block the main application</li>
<li>Periodic tasks (backups) need to run continuously</li>
<li>Allows main thread to remain responsive for API requests</li>
</ul>

</div>

#### 2. **StateMachineWorker** (`automation/workers/state_machine.py`)

<div style="background: #f3e5f5; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #9c27b0;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Responsibility:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>Coordinates execution of all state machines</li>
<li>Manages two execution modes:
    <ul style="margin-top: 0.5em; margin-bottom: 0.5em;">
    <li><strong>Sync</strong>: Sequential execution in main thread (cooperative)</li>
    <li><strong>Async</strong>: Parallel execution in separate threads (preemptive)</li>
    </ul>
</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Execution Modes:</strong>
</p>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 0.5em 0; font-weight: 500;">
<strong>Sync Mode (Cooperative Multitasking):</strong>
</p>

```python
# Machines execute sequentially, yielding control
for machine in sync_machines:
    machine.loop()  # Executes and schedules next run
    scheduler.call_later(interval, next_execution)
```

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0.5em 0; font-weight: 500;">
<strong>Async Mode (Preemptive Multitasking):</strong>
</p>

```python
# Each machine runs in its own thread
for machine in async_machines:
    thread = SchedThread(machine)
    thread.start()  # Runs independently
```

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0 0; font-weight: 500;">
<strong>Why a Worker?</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>State machines need to run continuously without blocking</li>
<li>Different machines may have different execution requirements</li>
<li>Enables true parallelism for independent processes</li>
</ul>

</div>

#### 3. **AsyncStateMachineWorker** (`automation/workers/state_machine.py`)

<div style="background: #fff3e0; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #ff9800;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Responsibility:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; padding-left: 1.5em; font-weight: 400;">
<li>Manages state machines that run in separate threads</li>
<li>Handles dynamic addition/removal of machines at runtime</li>
<li>Provides thread lifecycle management</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0 0; font-weight: 500;">
<strong>Why a Separate Worker?</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Some state machines need true parallelism (e.g., OPC UA server)</li>
<li>Allows machines to have blocking operations without affecting others</li>
<li>Enables independent failure isolation</li>
</ul>

</div>

### Worker Pattern Benefits

<div style="background: #fce4ec; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #e91e63;">

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Non-Blocking</strong>: Main application remains responsive</li>
<li><strong>Concurrency</strong>: Multiple tasks run simultaneously</li>
<li><strong>Isolation</strong>: Worker failures don't crash main application</li>
<li><strong>Resource Efficiency</strong>: Better CPU utilization through parallelism</li>
</ul>

</div>

---

---

## Component Interaction Flow

<div style="background: #f8f9fa; border-left: 5px solid #667eea; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<h3 style="color: #1a202c; font-size: 1.5em; margin-bottom: 1em; font-weight: 700;">
  🔄 Real-World Interaction Examples
</h3>

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<h4 style="color: #1b5e20; font-size: 1.3em; margin: 0 0 1em 0; font-weight: 700;">
  Example: Writing Tag Value to Database
</h4>

<div style="background: #ffffff; border-radius: 6px; padding: 1em; margin: 1em 0; border: 1px solid #4caf50;">

```
1. State Machine (Thread) updates tag in CVT
   │
   └─► CVTEngine (Thread-Safe)
          │
          ├─► Updates in-memory tag value
          └─► Notifies observers (including LoggerWorker queue)

2. LoggerWorker (Background Thread) wakes up
   │
   └─► Reads from queue
          │
          └─► DataLoggerEngine.query() (Thread-Safe)
                 │
                 ├─► Acquires lock
                 ├─► DataLogger.write_tags() (Actual DB operation)
                 └─► Releases lock, returns result

3. Database write completes
   │
   └─► LoggerWorker continues to next task
```

</div>

</div>

<div style="background: #ffebee; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #f44336;">

<h4 style="color: #b71c1c; font-size: 1.3em; margin: 0 0 1em 0; font-weight: 700;">
  Example: Creating an Alarm
</h4>

<div style="background: #ffffff; border-radius: 6px; padding: 1em; margin: 1em 0; border: 1px solid #f44336;">

```
1. API Handler receives request
   │
   └─► AlarmManager.append_alarm()
          │
          ├─► Validates business rules (duplicates, trigger values)
          ├─► Gets tag from CVTEngine (thread-safe)
          ├─► Creates Alarm instance
          ├─► Registers alarm in manager's registry
          └─► AlarmsLoggerEngine.query() (thread-safe DB write)
```

</div>

</div>

<div style="background: #f3e5f5; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #9c27b0;">

<h4 style="color: #4a148c; font-size: 1.3em; margin: 0 0 1em 0; font-weight: 700;">
  Example: State Machine Execution
</h4>

<div style="background: #ffffff; border-radius: 6px; padding: 1em; margin: 1em 0; border: 1px solid #9c27b0;">

```
1. Application starts
   │
   └─► StateMachineWorker.run()
          │
          ├─► Reads machines from StateMachineManager
          ├─► For each machine:
          │     ├─► If async: Creates SchedThread (separate thread)
          │     └─► If sync: Schedules in cooperative scheduler
          │
          └─► All machines run concurrently
                 │
                 ├─► Each machine reads from CVTEngine (thread-safe)
                 ├─► Each machine writes to CVTEngine (thread-safe)
                 └─► LoggerWorker periodically persists to DB
```

</div>

</div>

</div>

---

## Design Principles

<div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #667eea;">

<h3 style="color: #1a202c; font-size: 1.8em; margin-bottom: 1em; font-weight: 700;">
  🎯 Core Architectural Principles
</h3>

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<h4 style="color: #0d47a1; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #2196f3; padding-bottom: 0.5em;">
  Separation of Concerns
</h4>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Managers</strong>: <strong>What</strong> to do (business logic, coordination)</li>
<li><strong>Engines</strong>: <strong>How</strong> to do it safely (thread-safe operations)</li>
<li><strong>Workers</strong>: <strong>When</strong> to do it (background execution, scheduling)</li>
</ul>

</div>

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<h4 style="color: #1b5e20; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #4caf50; padding-bottom: 0.5em;">
  Single Responsibility Principle
</h4>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
Each component has one clear responsibility:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Managers</strong>: Orchestrate and coordinate</li>
<li><strong>Engines</strong>: Provide thread-safe access</li>
<li><strong>Workers</strong>: Execute background tasks</li>
</ul>

</div>

</div>

### Dependency Flow

<div style="background: #e1f5fe; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #03a9f4;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Dependency Flow:</strong>
</p>

```
Workers → Engines → Loggers → Database
   │         │
   └─────────┘
   (Workers use Engines for thread-safe operations)

Managers → Engines
   │
   └─► (Managers coordinate Engines)
```

</div>

### Thread Safety Hierarchy

<div style="background: #f3e5f5; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #9c27b0;">

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Workers</strong>: Run in separate threads (concurrency)</li>
<li><strong>Engines</strong>: Serialize access (thread-safety)</li>
<li><strong>Loggers</strong>: Perform actual operations (single-threaded execution)</li>
</ol>

</div>

---

## Common Patterns

<div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #4caf50;">

<h3 style="color: #1b5e20; font-size: 1.8em; margin-bottom: 1em; font-weight: 700;">
  🔧 Common Architectural Patterns
</h3>

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<h4 style="color: #0d47a1; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #2196f3; padding-bottom: 0.5em;">
  Pattern 1: Manager Uses Engine
</h4>

<div style="background: #ffffff; border-radius: 6px; padding: 1em; margin: 1em 0; border: 1px solid #2196f3;">

```python
class AlarmManager:
    def __init__(self):
        self.tag_engine = CVTEngine()  # Thread-safe tag access
    
    def append_alarm(self, ...):
        tag = self.tag_engine.get_tag_by_name(name)  # Thread-safe read
        # ... business logic ...
        self.alarms_engine.query(...)  # Thread-safe write
```

</div>

</div>

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<h4 style="color: #1b5e20; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #4caf50; padding-bottom: 0.5em;">
  Pattern 2: Worker Uses Engine
</h4>

<div style="background: #ffffff; border-radius: 6px; padding: 1em; margin: 1em 0; border: 1px solid #4caf50;">

```python
class LoggerWorker(BaseWorker):
    def __init__(self, manager):
        self.logger = DataLoggerEngine()  # Thread-safe DB access
    
    def run(self):
        while not self.stop_event.is_set():
            # Read from queue (thread-safe)
            tags = self.get_tags_from_queue()
            
            # Write via engine (thread-safe)
            self.logger.query({"action": "write_tags", ...})
            
            time.sleep(self._period)
```

</div>

</div>

<div style="background: #f3e5f5; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #9c27b0;">

<h4 style="color: #4a148c; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #9c27b0; padding-bottom: 0.5em;">
  Pattern 3: Manager Coordinates Multiple Engines
</h4>

<div style="background: #ffffff; border-radius: 6px; padding: 1em; margin: 1em 0; border: 1px solid #9c27b0;">

```python
class DBManager:
    def __init__(self):
        self.alarms_logger = AlarmsLoggerEngine()
        self.events_logger = EventsLoggerEngine()
        self.users_logger = UsersLoggerEngine()
        # ... coordinates all logging engines
```

</div>

</div>

</div>

---

## When to Use Each Component

<div style="background: linear-gradient(135deg, #fce4ec 0%, #f8bbd0 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #e91e63;">

<h3 style="color: #880e4f; font-size: 1.8em; margin-bottom: 1em; font-weight: 700;">
  🎯 Decision Guide
</h3>

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<h4 style="color: #0d47a1; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #2196f3; padding-bottom: 0.5em;">
  Use a <strong>Manager</strong> when:
</h4>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>✅ You need to coordinate multiple related resources</li>
<li>✅ You need to enforce business rules</li>
<li>✅ You need a high-level API for complex operations</li>
<li>✅ You need to maintain a registry of objects</li>
</ul>

</div>

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<h4 style="color: #1b5e20; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #4caf50; padding-bottom: 0.5em;">
  Use an <strong>Engine</strong> when:
</h4>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>✅ You need thread-safe access to shared resources</li>
<li>✅ Multiple threads will access the same resource</li>
<li>✅ You need to serialize database operations</li>
<li>✅ You need request-response pattern for async operations</li>
</ul>

</div>

<div style="background: #fce4ec; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #e91e63;">

<h4 style="color: #880e4f; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #e91e63; padding-bottom: 0.5em;">
  Use a <strong>Worker</strong> when:
</h4>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>✅ You need to run tasks periodically</li>
<li>✅ You need background processing</li>
<li>✅ You need non-blocking operations</li>
<li>✅ You need concurrent execution of independent tasks</li>
</ul>

</div>

</div>

---

## Summary

<div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #667eea;">

<h3 style="color: #1a202c; font-size: 1.8em; margin-bottom: 1em; font-weight: 700;">
  📋 Component Summary
</h3>

<div style="background: #ffffff; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; overflow-x: auto; border: 2px solid #667eea; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">

<table style="width: 100%; border-collapse: collapse; margin: 0;">
<thead>
<tr style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
<th style="padding: 1em; text-align: left; color: white; font-weight: 700; font-size: 1.1em; border: 1px solid #5a67d8;">Component</th>
<th style="padding: 1em; text-align: left; color: white; font-weight: 700; font-size: 1.1em; border: 1px solid #5a67d8;">Responsibility</th>
<th style="padding: 1em; text-align: left; color: white; font-weight: 700; font-size: 1.1em; border: 1px solid #5a67d8;">Problem Solved</th>
<th style="padding: 1em; text-align: left; color: white; font-weight: 700; font-size: 1.1em; border: 1px solid #5a67d8;">Key Pattern</th>
</tr>
</thead>
<tbody>
<tr style="background: #e3f2fd; border-bottom: 1px solid #bbdefb;">
<td style="padding: 1em; color: #1a202c; font-weight: 700; border: 1px solid #bbdefb;"><strong>Managers</strong></td>
<td style="padding: 1em; color: #1a202c; border: 1px solid #bbdefb;">Orchestration & Business Logic</td>
<td style="padding: 1em; color: #1a202c; border: 1px solid #bbdefb;">Resource coordination, business rules</td>
<td style="padding: 1em; color: #1a202c; border: 1px solid #bbdefb;">Singleton, Facade</td>
</tr>
<tr style="background: #e8f5e9; border-bottom: 1px solid #c8e6c9;">
<td style="padding: 1em; color: #1a202c; font-weight: 700; border: 1px solid #c8e6c9;"><strong>Engines</strong></td>
<td style="padding: 1em; color: #1a202c; border: 1px solid #c8e6c9;">Thread-Safe Access</td>
<td style="padding: 1em; color: #1a202c; border: 1px solid #c8e6c9;">Concurrency, race conditions</td>
<td style="padding: 1em; color: #1a202c; border: 1px solid #c8e6c9;">Request-Response, Locking</td>
</tr>
<tr style="background: #fce4ec; border-bottom: 1px solid #f8bbd0;">
<td style="padding: 1em; color: #1a202c; font-weight: 700; border: 1px solid #f8bbd0;"><strong>Workers</strong></td>
<td style="padding: 1em; color: #1a202c; border: 1px solid #f8bbd0;">Background Execution</td>
<td style="padding: 1em; color: #1a202c; border: 1px solid #f8bbd0;">Non-blocking, periodic tasks</td>
<td style="padding: 1em; color: #1a202c; border: 1px solid #f8bbd0;">Thread, Event-driven</td>
</tr>
</tbody>
</table>

</div>

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<h4 style="color: #0d47a1; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #2196f3; padding-bottom: 0.5em;">
  Key Takeaways
</h4>

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Managers</strong> = <strong>Orchestration</strong> (coordinate, manage, validate)</li>
<li><strong>Engines</strong> = <strong>Thread Safety</strong> (serialize, protect, synchronize)</li>
<li><strong>Workers</strong> = <strong>Concurrency</strong> (background, periodic, parallel)</li>
</ol>

</div>

<div style="background: #f8f9fa; border-left: 5px solid #667eea; padding: 1.5em; margin: 1.5em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 500;">
This architecture ensures that PyAutomation can handle the complex requirements of industrial automation systems: multiple concurrent operations, thread-safe data access, and responsive real-time processing.
</p>

</div>

</div>

---

## Engines vs Async Drivers: Threading vs Async Models

<div style="background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #ff9800;">

<h3 style="color: #bf360c; font-size: 1.8em; margin-bottom: 1em; font-weight: 700;">
  ⚡ Threading vs Async: When Are Engines Needed?
</h3>

<div style="background: #f8f9fa; border-left: 5px solid #ff9800; padding: 1.5em; margin: 1.5em 0; border-radius: 5px;">

<h4 style="color: #e65100; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #ff9800; padding-bottom: 0.5em;">
  The Question: Are Engines Necessary with Async Drivers?
</h4>

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
A common question when considering modern async frameworks (FastAPI + SQLAlchemy async + asyncpg) is: <strong>"Do I still need Engines if async drivers handle concurrency?"</strong>
</p>

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 700;">
The answer is: <strong>It depends on your concurrency model.</strong>
</p>

</div>

<div style="background: #ffebee; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #f44336;">

<h4 style="color: #b71c1c; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #f44336; padding-bottom: 0.5em;">
  Threading Model (Current PyAutomation)
</h4>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Architecture:</strong>
</p>

```
Multiple Threads → Engines (with locks) → Database
```

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0 0; font-weight: 500;">
<strong>Characteristics:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Multiple OS threads share resources</li>
<li>Preemptive multitasking (OS scheduler)</li>
<li>Race conditions possible</li>
<li><strong>Engines are necessary</strong> to serialize access with locks</li>
</ul>

</div>

<div style="background: #fff3e0; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #ff9800;">

<h5 style="color: #e65100; font-size: 1.2em; margin: 0 0 0.8em 0; font-weight: 700;">
  Example:
</h5>

<div style="background: #ffffff; border-radius: 5px; padding: 1em; margin: 0.5em 0; border: 1px solid #ff9800;">

```python
# Thread 1
engine.query({"action": "write_tag", ...})  # Acquires lock

# Thread 2 (concurrent)
engine.query({"action": "read_tag", ...})    # Waits for lock
```

</div>

</div>

<div style="background: #ffebee; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #f44336;">

<h5 style="color: #b71c1c; font-size: 1.2em; margin: 0 0 0.8em 0; font-weight: 700;">
  Why Engines are needed:
</h5>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Multiple threads can access database simultaneously</li>
<li>Peewee (synchronous ORM) is not thread-safe by default</li>
<li>Locks prevent race conditions and connection conflicts</li>
</ul>

</div>

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<h4 style="color: #1b5e20; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #4caf50; padding-bottom: 0.5em;">
  Async Model (FastAPI + asyncpg)
</h4>

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
<strong>Architecture:</strong>
</p>

```
Single Event Loop → Async Functions → Async Database Driver
```

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1em 0 0 0; font-weight: 500;">
<strong>Characteristics:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Single thread (event loop)</li>
<li>Cooperative multitasking (await/yield)</li>
<li>No race conditions (single-threaded execution)</li>
<li><strong>Engines are NOT needed</strong> for thread-safety</li>
</ul>

</div>

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<h5 style="color: #1b5e20; font-size: 1.2em; margin: 0 0 0.8em 0; font-weight: 700;">
  Example:
</h5>

<div style="background: #ffffff; border-radius: 5px; padding: 1em; margin: 0.5em 0; border: 1px solid #4caf50;">

```python
# FastAPI endpoint
@app.get("/tags/{tag_name}")
async def get_tag(tag_name: str):
    # No locks needed - event loop handles concurrency
    result = await db.execute(
        select(Tag).where(Tag.name == tag_name)
    )
    return result
```

</div>

</div>

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<h5 style="color: #1b5e20; font-size: 1.2em; margin: 0 0 0.8em 0; font-weight: 700;">
  Why Engines are NOT needed:
</h5>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li>Single event loop = no thread contention</li>
<li>Async drivers (asyncpg) handle connection pooling internally</li>
<li><code>await</code> provides natural serialization</li>
<li>No shared mutable state between concurrent operations</li>
</ul>

</div>

<div style="background: #fff3e0; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #ff9800;">

<h4 style="color: #e65100; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #ff9800; padding-bottom: 0.5em;">
  Key Differences
</h4>

<div style="background: #ffffff; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; overflow-x: auto; border: 2px solid #ff9800;">

<table style="width: 100%; border-collapse: collapse; margin: 0;">
<thead>
<tr style="background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%); color: #ffffff;">
<th style="padding: 12px; text-align: left; border: 2px solid #e65100; font-weight: 700; font-size: 1em;">Aspect</th>
<th style="padding: 12px; text-align: left; border: 2px solid #e65100; font-weight: 700; font-size: 1em;">Threading Model (PyAutomation)</th>
<th style="padding: 12px; text-align: left; border: 2px solid #e65100; font-weight: 700; font-size: 1em;">Async Model (FastAPI)</th>
</tr>
</thead>
<tbody>
<tr style="background: #fff3e0; border-bottom: 1px solid #ffcc80;">
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c; font-weight: 600;"><strong>Concurrency</strong></td>
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c;">Multiple OS threads</td>
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c;">Single event loop</td>
</tr>
<tr style="background: #ffffff; border-bottom: 1px solid #ffcc80;">
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c; font-weight: 600;"><strong>Synchronization</strong></td>
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c;">Locks (Engines)</td>
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c;"><code>await</code> keyword</td>
</tr>
<tr style="background: #fff3e0; border-bottom: 1px solid #ffcc80;">
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c; font-weight: 600;"><strong>Race Conditions</strong></td>
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c;">Possible (need locks)</td>
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c;">Not possible (single thread)</td>
</tr>
<tr style="background: #ffffff; border-bottom: 1px solid #ffcc80;">
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c; font-weight: 600;"><strong>Database Driver</strong></td>
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c;">Synchronous (Peewee)</td>
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c;">Async (asyncpg, async SQLAlchemy)</td>
</tr>
<tr style="background: #fff3e0; border-bottom: 1px solid #ffcc80;">
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c; font-weight: 600;"><strong>Engines Needed?</strong></td>
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c;"><strong>YES</strong> (for thread-safety)</td>
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c;"><strong>NO</strong> (for thread-safety)</td>
</tr>
<tr style="background: #ffffff;">
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c; font-weight: 600;"><strong>Blocking</strong></td>
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c;">Thread blocks on I/O</td>
<td style="padding: 12px; border: 1px solid #ffcc80; color: #1a202c;">Event loop switches tasks</td>
</tr>
</tbody>
</table>

</div>

<div style="background: #f8f9fa; border-left: 5px solid #ff9800; padding: 1.5em; margin: 1.5em 0; border-radius: 5px;">

<h4 style="color: #e65100; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #ff9800; padding-bottom: 0.5em;">
  When Would You Still Use Engines in Async?
</h4>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
Even in an async model, you might keep an "Engine-like" abstraction for:
</p>

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Business Logic Encapsulation</strong> (not thread-safety):
   ```python
   class TagEngine:
       async def get_tag_with_history(self, name: str):
           # Encapsulates complex query logic
           tag = await db.get_tag(name)
           history = await db.get_tag_history(name)
           return {"tag": tag, "history": history}
   ```
</li>

<li><strong>Request-Response Pattern</strong> (if needed):
   ```python
   class AsyncEngine:
       async def query(self, action: str, **params):
           # Still useful for abstraction, but no locks needed
           return await getattr(self, action)(**params)
   ```
</li>

<li><strong>Connection Pool Management</strong> (handled by async driver):
   ```python
   # asyncpg/SQLAlchemy async already handles this
   engine = create_async_engine(
       "postgresql+asyncpg://...",
       pool_size=20  # Connection pool managed by driver
   )
   ```
</li>

</ol>

</div>

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<h4 style="color: #0d47a1; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #2196f3; padding-bottom: 0.5em;">
  Migration Path: Threading → Async
</h4>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
If migrating PyAutomation to async:
</p>

<div style="background: #ffffff; border-radius: 5px; padding: 1em; margin: 1em 0; border: 1px solid #2196f3;">

<h5 style="color: #0d47a1; font-size: 1.2em; margin: 0 0 0.8em 0; font-weight: 700;">
  Current (Threading):
</h5>

```python
# Engine with locks
class DataLoggerEngine:
    def query(self, query_dict):
        self._request_lock.acquire()  # Serialize access
        result = self.logger.method(**query_dict["parameters"])
        self._request_lock.release()
        return result
```

</div>

<div style="background: #ffffff; border-radius: 5px; padding: 1em; margin: 1em 0; border: 1px solid #2196f3;">

<h5 style="color: #0d47a1; font-size: 1.2em; margin: 0 0 0.8em 0; font-weight: 700;">
  Async Equivalent:
</h5>

```python
# No locks needed - event loop handles concurrency
class DataLoggerEngine:
    async def query(self, query_dict):
        # No locks - await provides natural serialization
        result = await self.logger.method(**query_dict["parameters"])
        return result
```

</div>

<div style="background: #ffffff; border-radius: 5px; padding: 1em; margin: 1em 0; border: 1px solid #2196f3;">

<h5 style="color: #0d47a1; font-size: 1.2em; margin: 0 0 0.8em 0; font-weight: 700;">
  Workers → Async Tasks:
</h5>
```python
# Current: Thread-based worker
class LoggerWorker(BaseWorker):
    def run(self):
        while not self.stop_event.is_set():
            self.logger.query(...)
            time.sleep(self._period)

# Async: Background task
async def logger_task():
    while True:
        await logger.query(...)
        await asyncio.sleep(period)

# Start in FastAPI
@app.on_event("startup")
async def startup():
    asyncio.create_task(logger_task())
```

</div>

</div>

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<h4 style="color: #1b5e20; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #4caf50; padding-bottom: 0.5em;">
  Summary: Do Async Drivers Replace Engines?
</h4>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 700;">
<strong>For Thread-Safety: YES</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1.5em 0; padding-left: 1.5em; font-weight: 400;">
<li>Async drivers (asyncpg) + event loop eliminate the need for locks</li>
<li>Single-threaded execution = no race conditions</li>
<li>Connection pooling handled by driver</li>
</ul>

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 700;">
<strong>For Abstraction: MAYBE</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1.5em 0; padding-left: 1.5em; font-weight: 400;">
<li>You might still want Engine-like classes for:
    <ul style="margin-top: 0.5em; margin-bottom: 0.5em;">
    <li>Business logic encapsulation</li>
    <li>Consistent API patterns</li>
    <li>Code organization</li>
    </ul>
</li>
<li>But they won't need locks or thread-safety mechanisms</li>
</ul>

<div style="background: #fff3e0; border-left: 5px solid #ff9800; padding: 1.5em; margin: 1.5em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 700;">
<strong>Key Insight:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Threading model</strong>: Engines solve <strong>concurrency</strong> problem (locks)</li>
<li><strong>Async model</strong>: Event loop solves <strong>concurrency</strong> problem (cooperative multitasking)</li>
<li><strong>Engines in async</strong>: Optional for <strong>abstraction</strong>, not needed for <strong>safety</strong></li>
</ul>

</div>

</div>

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<h4 style="color: #1b5e20; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #4caf50; padding-bottom: 0.5em;">
  Real-World Example
</h4>

<div style="background: #ffffff; border-radius: 5px; padding: 1em; margin: 1em 0; border: 1px solid #4caf50;">

<h5 style="color: #1b5e20; font-size: 1.2em; margin: 0 0 0.8em 0; font-weight: 700;">
  FastAPI + asyncpg (No Engines Needed):
</h5>

```python
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import asyncpg

app = FastAPI()

# Connection pool managed by async driver
engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/db",
    pool_size=20
)

@app.get("/tags")
async def get_tags():
    async with AsyncSession(engine) as session:
        # No locks needed - event loop handles concurrency
        result = await session.execute(select(Tag))
        return result.scalars().all()

# Multiple concurrent requests handled safely by event loop
# No race conditions, no locks needed
```

</div>

<div style="background: #ffffff; border-radius: 5px; padding: 1em; margin: 1em 0; border: 1px solid #4caf50;">

<h5 style="color: #1b5e20; font-size: 1.2em; margin: 0 0 0.8em 0; font-weight: 700;">
  PyAutomation Current (Engines Required):
</h5>

```python
# Multiple threads accessing same engine
thread1: engine.query(...)  # Needs lock
thread2: engine.query(...)  # Waits for lock
thread3: engine.query(...)  # Waits for lock

# Engine serializes access with locks
```

</div>

</div>

<div style="background: #f8f9fa; border-left: 5px solid #ff9800; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<h4 style="color: #e65100; font-size: 1.4em; margin: 0 0 1em 0; font-weight: 700; border-bottom: 2px solid #ff9800; padding-bottom: 0.5em;">
  Conclusion
</h4>

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 700;">
<strong>In FastAPI + asyncpg:</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1.5em 0; padding-left: 1.5em; font-weight: 400;">
<li>✅ <strong>Async drivers handle concurrency</strong> (event loop + connection pooling)</li>
<li>✅ <strong>No locks needed</strong> (single-threaded execution)</li>
<li>✅ <strong>Engines not needed for thread-safety</strong></li>
<li>⚠️ <strong>Engines might still be useful for abstraction/organization</strong></li>
</ul>

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 700;">
<strong>In PyAutomation (current):</strong>
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1.5em 0; padding-left: 1.5em; font-weight: 400;">
<li>✅ <strong>Engines are essential</strong> (multiple threads need serialization)</li>
<li>✅ <strong>Locks prevent race conditions</strong></li>
<li>✅ <strong>Required for thread-safe database access</strong></li>
</ul>

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 500;">
The fundamental difference is the <strong>concurrency model</strong>:
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0.5em 0 0 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Threading</strong>: Preemptive → Need locks → Engines provide locks</li>
<li><strong>Async</strong>: Cooperative → Event loop → No locks needed</li>
</ul>

</div>

</div>

</div>

