# Architecture Overview

PyAutomation is built on a modular architecture designed for high concurrency and reliability in industrial environments. The system is composed of several key layers that interact to acquire, process, store, and visualize data.

![Core Architecture](img/PyAutomationCore.svg)

## Core Components

### 1. PyAutomation Core

The central hub of the framework. It manages the lifecycle of all other components, initializes the singleton instances, and handles the main application loop. It ensures that services like the Logger, State Machines, and API are synchronized.

### 2. State Machine Engine

The heart of the logic processing. PyAutomation allows you to define finite state machines (FSM) that run in parallel threads.

- **DAQ (Data Acquisition)**: Specialized state machines for polling data from external devices.
- **Process Logic**: Custom state machines that implement your specific automation logic (e.g., control loops, sequence management).

### 3. CVT (Current Value Table)

A high-performance, in-memory data store.

- Acts as the "Single Source of Truth" for real-time data.
- All tags (variables) are stored here.
- Provides thread-safe access for readers (UI, API, Loggers) and writers (Drivers, Logic).

### 4. Connectivity Layers

- **OPC UA Client**: Connects to field devices (PLCs, Sensors) to read/write data. Supports subscription-based (DAS) and polling-based (DAQ) acquisition.
- **OPC UA Server**: Exposes internal data to external systems (e.g., higher-level SCADA or ERP systems), acting as a gateway.

### 5. Data Persistence & Logging

- **Data Logger**: Periodically samples data from the CVT and stores it in the database (SQLite/PostgreSQL) for historical trending.
- **Alarm Manager**: Monitors tags against defined conditions (High, Low, Digital) and manages alarm states (Active, Acknowledged, Cleared). Logged to the database compliant with ISA 18.2.
- **Event Logger**: Captures system events and operator actions.

### 6. Interface & API

- **Web API (Flask/RestX)**: RESTful endpoints to configure the system, query historical data, and manage users.
- **Real-time Web Socket (Socket.IO)**: Pushes updates to the frontend for live visualization without polling.
- **Dash/React Frontend**: A customizable web interface for HMI/SCADA screens.

## Data Flow

1.  **Acquisition**: The **OPC UA Client** receives data changes from field devices.
2.  **Update**: This data updates the **CVT** immediately.
3.  **Notify**: The CVT notifies registered observers (e.g., **Alarm Manager**, **State Machines**).
4.  **Process**: **State Machines** execute logic based on new values.
5.  **Store**: The **Data Logger** saves significant changes or periodic samples to the **Database**.
6.  **Visualize**: The **Socket.IO** server pushes the new CVT values to connected web clients for real-time display.
