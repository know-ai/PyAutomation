# User Guide

Welcome to the PyAutomation User Guide. This comprehensive manual is designed to assist you in effectively navigating and utilizing the PyAutomation platform for industrial automation and control.

PyAutomation is a modular tool designed to streamline the management of industrial systems through its core components: **Tags**, **Communications**, **Database**, and **Alarms**.

## Objective

The goal of this manual is to empower operators and engineers to maximize the potential of PyAutomation. By following these guides, you will be able to set up a reliable, efficient, and secure automation environment. Each section includes detailed instructions and visual aids to facilitate the learning process.

## Modules Overview

### [Tags Module](Tags/index.md)

The **Tags Module** acts as the central nervous system of your automation project. It allows you to create, configure, and manage data points (tags) that represent real-world variables such as sensors, actuators, and control parameters. This section covers tag creation, property configuration, and lifecycle management.

### [Communications Module](Communications/index.md)

The **Communications Module** handles external connectivity, specifically focusing on OPC UA (Open Platform Communications Unified Architecture) server management. This section guides you through configuring OPC UA servers to ensure seamless interoperability between PyAutomation and other industrial devices or SCADA systems.

### [Database Module](Database/index.md)

The **Database Module** manages the persistence of historical data. It enables connection to various database systems for logging tag values, alarms, and events. This section explains how to configure database connections, ensuring data integrity and availability for trend analysis and auditing.

### [Alarms Module](Alarms/index.md)

The **Alarms Module** provides robust fault detection and notification capabilities. It allows you to define alarm conditions based on tag values, configure thresholds, and manage alarm states (acknowledgment, shelving, suppression). This section details the process of setting up and managing alarms to maintain operational safety.

### [Users Module](Users/index.md)

The **Users Module** manages user accounts, authentication, and password operations. It provides role-based access control (RBAC) with different permission levels, allowing you to manage user credentials, change passwords, and reset forgotten passwords following proper authorization rules. This section covers user authentication, password management, and security best practices.

### [Settings Module](Settings/index.md)

The **Settings Module** provides configuration management capabilities, allowing you to export and import system configuration. This includes all configuration tables (tags, alarms, users, OPC UA settings, etc.) while preserving historical data. This section covers how to create backups, migrate configurations between systems, and restore settings from previous exports.

### [OPC UA Server Module](OPCUAServer/index.md)

The **OPC UA Server Module** manages PyAutomation's embedded OPC UA Server, which exposes your automation data (tags, alarms, and state machines) to external OPC UA clients. This section covers viewing exposed attributes, configuring access permissions, and understanding the server's address space structure for seamless integration with SCADA systems and other industrial applications.

### [Real-Time Trends Module](RealTimeTrends/index.md)

The **Real-Time Trends Module** provides powerful visualization capabilities through configurable strip charts for monitoring process variables in real-time. This section covers creating custom dashboards, configuring charts with multiple tags, managing buffer sizes, and switching between edit and production modes for optimal operational monitoring.

### [Machines Module](Machines/index.md)

The **Machines Module** provides comprehensive monitoring and management of state machines (engines) running in the PyAutomation system. This section covers viewing machine states, configuring execution intervals, performing state transitions, and understanding the lifecycle of automation engines that execute control logic and data processing.

### [Events Module](Events/index.md)

The **Events Module** provides comprehensive tracking and analysis of system events, including user actions, system notifications, alarm state changes, and other significant occurrences. This section covers filtering events by multiple criteria, adding comments, searching event history, and using events as an audit trail for system behavior analysis.

### [Operational Logs Module](OperationalLogs/index.md)

The **Operational Logs Module** provides a detailed audit trail of operational activities, system messages, and application-level logs. This section covers creating operational logs, linking logs to alarms and events, filtering log data, and using logs for documentation, incident analysis, and compliance reporting.


