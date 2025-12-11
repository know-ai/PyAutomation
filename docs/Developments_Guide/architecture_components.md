# Architecture Components: Workers, Engines, and Managers

This document provides a technical explanation of the three fundamental architectural components in PyAutomation: **Workers**, **Engines**, and **Managers**. Understanding these components is crucial for developers working with or extending the framework.

## Overview

PyAutomation follows a **layered architecture** that separates concerns into three distinct component types, each solving specific problems in industrial automation systems:

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

## Managers - Orchestration Layer

### Purpose and Responsibility

**Managers** are **orchestration components** that coordinate business logic and manage the lifecycle of related resources. They act as **facades** that provide high-level APIs for complex operations involving multiple subsystems.

### Problems They Solve

1. **Resource Coordination**: Managing collections of related objects (alarms, state machines, database connections)
2. **Business Logic**: Implementing domain-specific rules and workflows
3. **Lifecycle Management**: Creating, updating, deleting, and querying resources
4. **Cross-System Integration**: Coordinating between CVT, database, and external systems

### Key Characteristics

- **Singleton Pattern**: One instance per application
- **High-Level API**: Provide convenient methods for common operations
- **State Management**: Maintain registries of managed resources
- **Business Rules**: Enforce validation and business logic

### Managers in PyAutomation

#### 1. **DBManager** (`automation/managers/db.py`)

**Responsibility:**
- Central coordinator for all database operations
- Manages database connection lifecycle
- Initializes and coordinates multiple logging engines
- Registers database models and handles table creation

**Key Operations:**
```python
# Manages database connection
db_manager.set_db(database_instance)

# Coordinates multiple engines
db_manager.alarms_logger.query(...)
db_manager.events_logger.query(...)
db_manager.users_logger.query(...)
```

**Why a Manager?**
- Single point of coordination for all database-related operations
- Ensures consistent database configuration across all engines
- Manages the relationship between CVT and database persistence

#### 2. **AlarmManager** (`automation/managers/alarms.py`)

**Responsibility:**
- Manages the collection of all alarms in the system
- Validates alarm configurations (duplicate checks, trigger value validation)
- Coordinates between CVT (for tag values) and alarm state machines
- Handles real-time communication via SocketIO

**Key Operations:**
```python
# Create and register alarm
alarm_manager.append_alarm(name, tag, type, trigger_value)

# Retrieve alarm
alarm = alarm_manager.get_alarm_by_name(name)

# Update alarm state
alarm_manager.update_alarm(name, ...)
```

**Why a Manager?**
- Central registry prevents duplicate alarms
- Enforces business rules (e.g., one alarm type per tag)
- Coordinates alarm lifecycle with CVT observers

#### 3. **StateMachineManager** (`automation/managers/state_machine.py`)

**Responsibility:**
- Registry of all state machines in the system
- Manages execution configuration (intervals, sync/async mode)
- Provides serialization for API responses

**Key Operations:**
```python
# Register state machine
state_machine_manager.append_machine(machine)

# Get all machines with configuration
machines = state_machine_manager.get_machines()  # Returns [(machine, interval, mode), ...]
```

**Why a Manager?**
- Single source of truth for all state machines
- Enables workers to discover and execute machines
- Provides configuration management

#### 4. **OPCUAClientManager** (`automation/managers/opcua_client.py`)

**Responsibility:**
- Manages multiple OPC UA client connections
- Handles client lifecycle (connect, disconnect, reconnect)
- Coordinates subscriptions and data flow to CVT

**Key Operations:**
```python
# Add OPC UA client
opcua_client_manager.add_client(url, client_name)

# Subscribe tag to OPC UA node
opcua_client_manager.subscribe(tag, address, namespace)
```

**Why a Manager?**
- Manages multiple concurrent OPC UA connections
- Handles reconnection logic and connection pooling
- Coordinates data flow from external systems to CVT

### Manager Pattern Benefits

- **Single Responsibility**: Each manager focuses on one domain (alarms, database, state machines)
- **Encapsulation**: Hides complexity of coordinating multiple engines
- **Consistency**: Ensures business rules are applied uniformly
- **Testability**: Managers can be mocked for testing dependent components

---

## Engines - Thread-Safe Processing Layer

### Purpose and Responsibility

**Engines** are **thread-safe wrappers** that provide synchronized access to shared resources (primarily database operations). They solve the **concurrency problem** in multi-threaded industrial systems.

### Problems They Solve

1. **Thread Safety**: Prevent race conditions when multiple threads access shared resources
2. **Database Concurrency**: Ensure safe database operations from multiple threads
3. **Request-Response Pattern**: Provide synchronous-like interface for asynchronous operations
4. **Resource Locking**: Coordinate access to singleton resources

### Key Characteristics

- **Singleton Pattern**: One instance shared across all threads
- **Thread-Safe**: Uses locks to serialize access
- **Request-Response**: Queues requests and waits for responses
- **Wrapper Pattern**: Wraps a Logger (BaseLogger) that does actual work

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

**Responsibility:**
- Thread-safe access to tag value logging operations
- Provides methods for reading/writing historical tag data
- Handles tabular data queries with pagination

**Thread Safety Mechanism:**
```python
# Request
engine.request({"action": "read_tabular_data", "parameters": {...}})

# Response (waits for completion)
result = engine.response()  # Blocks until operation completes
```

**Why an Engine?**
- Multiple threads (workers, API handlers) may query historical data simultaneously
- Prevents database connection conflicts and race conditions
- Ensures data consistency during concurrent reads/writes

#### 2. **AlarmsLoggerEngine** (`automation/logger/alarms.py`)

**Responsibility:**
- Thread-safe access to alarm summary/history operations
- Manages alarm state persistence
- Provides paginated alarm history queries

**Why an Engine?**
- Alarm state changes can occur from multiple threads (state machines, API, user actions)
- Prevents concurrent modification of alarm records
- Ensures alarm history is written atomically

#### 3. **CVTEngine** (`automation/tags/cvt.py`)

**Responsibility:**
- Thread-safe access to the Current Value Table (CVT)
- Manages tag creation, updates, and queries
- Coordinates observer notifications

**Thread Safety:**
- Uses thread-safe dictionaries and locks
- Provides atomic tag updates
- Ensures observers are notified correctly

**Why an Engine?**
- CVT is accessed by multiple threads simultaneously:
  - State machines reading tag values
  - OPC UA clients writing values
  - API handlers reading values
  - Logger workers reading for persistence
- Prevents data corruption and ensures consistency

#### 4. **EventsLoggerEngine**, **UsersLoggerEngine**, **LogsLoggerEngine**, etc.

**Responsibility:**
- Thread-safe access to their respective domain operations
- Each follows the same pattern: Engine → Logger → Database

### Engine Pattern Benefits

- **Thread Safety**: Eliminates race conditions in multi-threaded environments
- **Consistency**: Ensures operations complete atomically
- **Predictability**: Request-response pattern makes async operations appear synchronous
- **Resource Protection**: Prevents concurrent access to shared resources (database, CVT)

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

### Purpose and Responsibility

**Workers** are **background threads** that execute periodic or continuous tasks. They run independently of the main application thread, enabling concurrent processing.

### Problems They Solve

1. **Non-Blocking Operations**: Prevent long-running tasks from blocking the main thread
2. **Periodic Tasks**: Execute tasks at regular intervals (data logging, health checks)
3. **Concurrent Execution**: Run multiple state machines in parallel
4. **Resource Management**: Handle background maintenance (database backups, reconnections)

### Key Characteristics

- **Thread-Based**: Extend `threading.Thread` or use `BaseWorker`
- **Lifecycle Management**: Start, stop, and join operations
- **Event-Driven**: Use `threading.Event` for graceful shutdown
- **Daemon Threads**: Can be daemon threads that terminate with main process

### Workers in PyAutomation

#### 1. **LoggerWorker** (`automation/workers/logger.py`)

**Responsibility:**
- Periodically writes tag values from CVT to database
- Performs database maintenance (backups, vacuuming)
- Monitors and reconnects OPC UA clients
- Runs in background thread, independent of main application

**Execution Pattern:**
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

**Why a Worker?**
- Database writes should not block the main application
- Periodic tasks (backups) need to run continuously
- Allows main thread to remain responsive for API requests

#### 2. **StateMachineWorker** (`automation/workers/state_machine.py`)

**Responsibility:**
- Coordinates execution of all state machines
- Manages two execution modes:
  - **Sync**: Sequential execution in main thread (cooperative)
  - **Async**: Parallel execution in separate threads (preemptive)

**Execution Modes:**

**Sync Mode (Cooperative Multitasking):**
```python
# Machines execute sequentially, yielding control
for machine in sync_machines:
    machine.loop()  # Executes and schedules next run
    scheduler.call_later(interval, next_execution)
```

**Async Mode (Preemptive Multitasking):**
```python
# Each machine runs in its own thread
for machine in async_machines:
    thread = SchedThread(machine)
    thread.start()  # Runs independently
```

**Why a Worker?**
- State machines need to run continuously without blocking
- Different machines may have different execution requirements
- Enables true parallelism for independent processes

#### 3. **AsyncStateMachineWorker** (`automation/workers/state_machine.py`)

**Responsibility:**
- Manages state machines that run in separate threads
- Handles dynamic addition/removal of machines at runtime
- Provides thread lifecycle management

**Why a Separate Worker?**
- Some state machines need true parallelism (e.g., OPC UA server)
- Allows machines to have blocking operations without affecting others
- Enables independent failure isolation

### Worker Pattern Benefits

- **Non-Blocking**: Main application remains responsive
- **Concurrency**: Multiple tasks run simultaneously
- **Isolation**: Worker failures don't crash main application
- **Resource Efficiency**: Better CPU utilization through parallelism

---

## Component Interaction Flow

### Example: Writing Tag Value to Database

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

### Example: Creating an Alarm

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

### Example: State Machine Execution

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

---

## Design Principles

### Separation of Concerns

- **Managers**: **What** to do (business logic, coordination)
- **Engines**: **How** to do it safely (thread-safe operations)
- **Workers**: **When** to do it (background execution, scheduling)

### Single Responsibility Principle

Each component has one clear responsibility:
- **Managers**: Orchestrate and coordinate
- **Engines**: Provide thread-safe access
- **Workers**: Execute background tasks

### Dependency Flow

```
Workers → Engines → Loggers → Database
   │         │
   └─────────┘
   (Workers use Engines for thread-safe operations)

Managers → Engines
   │
   └─► (Managers coordinate Engines)
```

### Thread Safety Hierarchy

1. **Workers**: Run in separate threads (concurrency)
2. **Engines**: Serialize access (thread-safety)
3. **Loggers**: Perform actual operations (single-threaded execution)

---

## Common Patterns

### Pattern 1: Manager Uses Engine

```python
class AlarmManager:
    def __init__(self):
        self.tag_engine = CVTEngine()  # Thread-safe tag access
    
    def append_alarm(self, ...):
        tag = self.tag_engine.get_tag_by_name(name)  # Thread-safe read
        # ... business logic ...
        self.alarms_engine.query(...)  # Thread-safe write
```

### Pattern 2: Worker Uses Engine

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

### Pattern 3: Manager Coordinates Multiple Engines

```python
class DBManager:
    def __init__(self):
        self.alarms_logger = AlarmsLoggerEngine()
        self.events_logger = EventsLoggerEngine()
        self.users_logger = UsersLoggerEngine()
        # ... coordinates all logging engines
```

---

## When to Use Each Component

### Use a **Manager** when:
- ✅ You need to coordinate multiple related resources
- ✅ You need to enforce business rules
- ✅ You need a high-level API for complex operations
- ✅ You need to maintain a registry of objects

### Use an **Engine** when:
- ✅ You need thread-safe access to shared resources
- ✅ Multiple threads will access the same resource
- ✅ You need to serialize database operations
- ✅ You need request-response pattern for async operations

### Use a **Worker** when:
- ✅ You need to run tasks periodically
- ✅ You need background processing
- ✅ You need non-blocking operations
- ✅ You need concurrent execution of independent tasks

---

## Summary

| Component | Responsibility | Problem Solved | Key Pattern |
|-----------|---------------|----------------|-------------|
| **Managers** | Orchestration & Business Logic | Resource coordination, business rules | Singleton, Facade |
| **Engines** | Thread-Safe Access | Concurrency, race conditions | Request-Response, Locking |
| **Workers** | Background Execution | Non-blocking, periodic tasks | Thread, Event-driven |

### Key Takeaways

1. **Managers** = **Orchestration** (coordinate, manage, validate)
2. **Engines** = **Thread Safety** (serialize, protect, synchronize)
3. **Workers** = **Concurrency** (background, periodic, parallel)

This architecture ensures that PyAutomation can handle the complex requirements of industrial automation systems: multiple concurrent operations, thread-safe data access, and responsive real-time processing.

---

## Engines vs Async Drivers: Threading vs Async Models

### The Question: Are Engines Necessary with Async Drivers?

A common question when considering modern async frameworks (FastAPI + SQLAlchemy async + asyncpg) is: **"Do I still need Engines if async drivers handle concurrency?"**

The answer is: **It depends on your concurrency model.**

### Threading Model (Current PyAutomation)

**Architecture:**
```
Multiple Threads → Engines (with locks) → Database
```

**Characteristics:**
- Multiple OS threads share resources
- Preemptive multitasking (OS scheduler)
- Race conditions possible
- **Engines are necessary** to serialize access with locks

**Example:**
```python
# Thread 1
engine.query({"action": "write_tag", ...})  # Acquires lock

# Thread 2 (concurrent)
engine.query({"action": "read_tag", ...})    # Waits for lock
```

**Why Engines are needed:**
- Multiple threads can access database simultaneously
- Peewee (synchronous ORM) is not thread-safe by default
- Locks prevent race conditions and connection conflicts

### Async Model (FastAPI + asyncpg)

**Architecture:**
```
Single Event Loop → Async Functions → Async Database Driver
```

**Characteristics:**
- Single thread (event loop)
- Cooperative multitasking (await/yield)
- No race conditions (single-threaded execution)
- **Engines are NOT needed** for thread-safety

**Example:**
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

**Why Engines are NOT needed:**
- Single event loop = no thread contention
- Async drivers (asyncpg) handle connection pooling internally
- `await` provides natural serialization
- No shared mutable state between concurrent operations

### Key Differences

| Aspect | Threading Model (PyAutomation) | Async Model (FastAPI) |
|-------|-------------------------------|----------------------|
| **Concurrency** | Multiple OS threads | Single event loop |
| **Synchronization** | Locks (Engines) | `await` keyword |
| **Race Conditions** | Possible (need locks) | Not possible (single thread) |
| **Database Driver** | Synchronous (Peewee) | Async (asyncpg, async SQLAlchemy) |
| **Engines Needed?** | **YES** (for thread-safety) | **NO** (for thread-safety) |
| **Blocking** | Thread blocks on I/O | Event loop switches tasks |

### When Would You Still Use Engines in Async?

Even in an async model, you might keep an "Engine-like" abstraction for:

1. **Business Logic Encapsulation** (not thread-safety):
   ```python
   class TagEngine:
       async def get_tag_with_history(self, name: str):
           # Encapsulates complex query logic
           tag = await db.get_tag(name)
           history = await db.get_tag_history(name)
           return {"tag": tag, "history": history}
   ```

2. **Request-Response Pattern** (if needed):
   ```python
   class AsyncEngine:
       async def query(self, action: str, **params):
           # Still useful for abstraction, but no locks needed
           return await getattr(self, action)(**params)
   ```

3. **Connection Pool Management** (handled by async driver):
   ```python
   # asyncpg/SQLAlchemy async already handles this
   engine = create_async_engine(
       "postgresql+asyncpg://...",
       pool_size=20  # Connection pool managed by driver
   )
   ```

### Migration Path: Threading → Async

If migrating PyAutomation to async:

**Current (Threading):**
```python
# Engine with locks
class DataLoggerEngine:
    def query(self, query_dict):
        self._request_lock.acquire()  # Serialize access
        result = self.logger.method(**query_dict["parameters"])
        self._request_lock.release()
        return result
```

**Async Equivalent:**
```python
# No locks needed - event loop handles concurrency
class DataLoggerEngine:
    async def query(self, query_dict):
        # No locks - await provides natural serialization
        result = await self.logger.method(**query_dict["parameters"])
        return result
```

**Workers → Async Tasks:**
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

### Summary: Do Async Drivers Replace Engines?

**For Thread-Safety: YES**
- Async drivers (asyncpg) + event loop eliminate the need for locks
- Single-threaded execution = no race conditions
- Connection pooling handled by driver

**For Abstraction: MAYBE**
- You might still want Engine-like classes for:
  - Business logic encapsulation
  - Consistent API patterns
  - Code organization
- But they won't need locks or thread-safety mechanisms

**Key Insight:**
- **Threading model**: Engines solve **concurrency** problem (locks)
- **Async model**: Event loop solves **concurrency** problem (cooperative multitasking)
- **Engines in async**: Optional for **abstraction**, not needed for **safety**

### Real-World Example

**FastAPI + asyncpg (No Engines Needed):**
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

**PyAutomation Current (Engines Required):**
```python
# Multiple threads accessing same engine
thread1: engine.query(...)  # Needs lock
thread2: engine.query(...)  # Waits for lock
thread3: engine.query(...)  # Waits for lock

# Engine serializes access with locks
```

### Conclusion

**In FastAPI + asyncpg:**
- ✅ **Async drivers handle concurrency** (event loop + connection pooling)
- ✅ **No locks needed** (single-threaded execution)
- ✅ **Engines not needed for thread-safety**
- ⚠️ **Engines might still be useful for abstraction/organization**

**In PyAutomation (current):**
- ✅ **Engines are essential** (multiple threads need serialization)
- ✅ **Locks prevent race conditions**
- ✅ **Required for thread-safe database access**

The fundamental difference is the **concurrency model**:
- **Threading**: Preemptive → Need locks → Engines provide locks
- **Async**: Cooperative → Event loop → No locks needed

