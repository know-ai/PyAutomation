# PyAutomation User Guide

Welcome to the **PyAutomation User Guide** - your comprehensive resource for mastering industrial automation and control with PyAutomation.

![PyAutomation Dashboard](images/FirstPageAfterLogin.png)

*Figure 1: PyAutomation 2.0.0 Modern React Interface*

## What's New in Version 2.0.0

**PyAutomation 2.0.0** introduces a **revolutionary modern web interface** built with **React**, delivering an exceptional user experience that combines powerful industrial automation capabilities with intuitive, responsive design.

### Key Improvements

*   **Modern React Interface**: Fast, responsive, and intuitive user experience
*   **Real-Time Updates**: Live data visualization without page refreshes
*   **Enhanced Visualization**: Advanced strip charts and trend analysis
*   **Improved Navigation**: Streamlined sidebar and intuitive module organization
*   **Better Performance**: Optimized rendering and efficient data handling
*   **Mobile-Friendly**: Responsive design that adapts to different screen sizes

![Sidebar Navigation](images/Sidebar.png)

*Figure 2: Modern sidebar navigation with all modules accessible*

## Objective

This comprehensive manual empowers operators and engineers to maximize PyAutomation's potential. By following these guides, you'll set up a reliable, efficient, and secure automation environment. Each section includes detailed instructions, visual aids, and best practices to facilitate your learning journey.

## Core Modules Overview

PyAutomation is a modular platform designed to streamline industrial system management. Below is an overview of each module and its key capabilities:

---

### [Tags Module](Tags/index.md)

The **Tags Module** is the central nervous system of your automation project, managing all data points that represent real-world process variables.

**Key Features:**
*   **Comprehensive Tag Management**: Create, edit, and delete tags with intuitive forms
*   **Advanced Filtering**: Gaussian and process filters for noise reduction
*   **Anomaly Detection**: Built-in frozen data, outlier, and out-of-range detection
*   **OPC UA Integration**: Seamless connection to external OPC UA servers
*   **Metadata Organization**: Segment and manufacturer classification for better organization
*   **Export Capabilities**: CSV export for backup and analysis

![Tags Dashboard](images/TagsCreated.png)

*Figure 3: Tags module showing organized tag management*

---

### [Communications Module](Communications/index.md)

The **Communications Module** handles external connectivity, enabling seamless integration with industrial devices and SCADA systems.

**Key Features:**
*   **OPC UA Client Management**: Connect to multiple OPC UA servers simultaneously
*   **Node Browser**: Visual exploration of OPC UA address spaces
*   **Multi-Selection**: Efficient tag selection with Ctrl+Click support
*   **Polling Configuration**: Flexible scan time configuration per connection
*   **Connection Status**: Real-time monitoring of communication health

![OPC UA Explorer](images/OPCUAExplorer.png)

*Figure 4: OPC UA node browser for exploring server address spaces*

---

### [Database Module](Database/index.md)

The **Database Module** ensures reliable data persistence for historical analysis, auditing, and compliance.

**Key Features:**
*   **Multi-Database Support**: PostgreSQL, MySQL, and SQLite compatibility
*   **Automatic Schema Creation**: Tables created automatically on first connection
*   **Historical Data Logging**: Comprehensive data retention for trends and analysis
*   **Easy Configuration**: Simple connection setup through intuitive forms
*   **Data Integrity**: Robust transaction management and error handling

![Database Configuration](images/DatabaseConfigInNavBar.png)

*Figure 5: Database configuration interface*

---

### [Alarms Module](Alarms/index.md)

The **Alarms Module** provides enterprise-grade alarm management following ISA-18.2 standards, ensuring operational safety and compliance.

**Key Features:**
*   **Multiple Alarm Types**: BOOL, HIGH, LOW, HIGH-HIGH, LOW-LOW triggers
*   **State Management**: Complete lifecycle tracking (Normal, Unacknowledged, Acknowledged, Shelved, etc.)
*   **Alarm Actions**: Acknowledge, shelve, unshelve, and return to service
*   **Alarm History**: Comprehensive audit trail of all alarm state changes
*   **Export Functionality**: CSV export for compliance reporting
*   **Real-Time Monitoring**: Live alarm status updates

![Alarms Dashboard](images/AlarmsDashboard_WithAlarms.png)

*Figure 6: Alarms dashboard with real-time status monitoring*

---

### [OPC UA Server Module](OPCUAServer/index.md)

The **OPC UA Server Module** exposes your automation data to external systems, enabling seamless integration with SCADA, HMIs, and other industrial applications.

**Key Features:**
*   **Embedded Server**: Built-in OPC UA server running as a state machine
*   **Three Main Folders**: Organized data structure (CVT, Alarms, Engines)
*   **Access Control**: Configurable read/write permissions per variable
*   **Real-Time Updates**: Continuous data publishing
*   **Standard Protocol**: Industry-standard OPC UA for maximum compatibility

---

### [Real-Time Trends Module](RealTimeTrends/index.md)

The **Real-Time Trends Module** provides powerful visualization capabilities through configurable strip charts for live process monitoring.

**Key Features:**
*   **Multiple Strip Charts**: Create unlimited custom dashboards
*   **Edit & Production Modes**: Switch between configuration and locked viewing modes
*   **Drag & Resize**: Flexible layout customization
*   **Multiple Tags Per Chart**: Display related variables together
*   **Dual Y-Axes**: Support for different units on the same chart
*   **Configurable Buffers**: Control historical data retention
*   **Persistent Layouts**: Automatic saving of dashboard configurations

![Real-Time Trends Production Mode](images/RealTimeStripChartIntoProductionMode.png)

*Figure 7: Real-time strip charts displaying live process data*

---

### [Machines Module](Machines/index.md)

The **Machines Module** provides comprehensive monitoring and management of state machines (engines) that execute control logic and data processing.

**Key Features:**
*   **State Monitoring**: Real-time view of all state machine states
*   **Interval Configuration**: Adjust execution intervals for performance tuning
*   **State Transitions**: Manual control of machine lifecycles
*   **Lifecycle Tracking**: Complete state history (Starting, Waiting, Running, Resetting)
*   **Performance Optimization**: Fine-tune system performance through interval management

![Machines Dashboard](images/MachinePage.png)

*Figure 8: State machines monitoring and management interface*

---

### [Events Module](Events/index.md)

The **Events Module** provides comprehensive tracking and analysis of system events, serving as a complete audit trail for system behavior.

**Key Features:**
*   **Comprehensive Filtering**: Filter by user, priority, criticality, classification, and date range
*   **Date Range Presets**: Quick selection of common time ranges
*   **Custom Date Ranges**: Flexible time period definition
*   **Comments System**: Add context and notes to events
*   **Export Capabilities**: CSV export for external analysis
*   **Real-Time Updates**: Live event stream monitoring

![Events Dashboard](images/EventPage.png)

*Figure 9: Events module with advanced filtering capabilities*

---

### [Operational Logs Module](OperationalLogs/index.md)

The **Operational Logs Module** provides a detailed audit trail of operational activities, enabling complete traceability and documentation.

**Key Features:**
*   **Log Creation**: Manual log entry for operational documentation
*   **Alarm & Event Linking**: Associate logs with specific alarms or events
*   **Advanced Filtering**: Filter by user, alarm, date range, and classification
*   **Comprehensive Search**: Search by message or description content
*   **Export Functionality**: CSV export for reporting and compliance
*   **Traceability**: Complete chain of documentation for incidents

![Operational Logs](images/OperationalLog.png)

*Figure 10: Operational logs interface for documentation and traceability*

---

### [Users Module](Users/index.md)

The **Users Module** provides robust user management with role-based access control (RBAC) for secure system operation.

**Key Features:**
*   **Role-Based Access Control**: Admin, Operator, and Guest roles
*   **Password Management**: Secure password policies and reset capabilities
*   **User Administration**: Create, edit, and manage user accounts
*   **Security Best Practices**: Following industry standards for authentication
*   **Audit Trail**: Complete logging of user management activities

![User Management](images/UserManagementPage.png)

*Figure 11: User management interface with role-based access control*

---

### [Settings Module](Settings/index.md)

The **Settings Module** centralizes system configuration management, enabling easy backup, migration, and restoration.

**Key Features:**
*   **Configuration Export**: Complete system configuration backup
*   **Configuration Import**: Restore or migrate configurations
*   **Logger Configuration**: Adjust log levels and rotation settings
*   **System Parameters**: Centralized system-wide settings
*   **Version Control**: Maintain configuration history

![System Settings](images/SystemSettingsPage.png)

*Figure 12: System settings and configuration management*

---

## Getting Started

Ready to begin? Here's your quick start path:

1.   **Start with the Basics**: 
     *   Review the [Quick Start Guide](QuickStart.md) for Docker deployment
     *   Set up your database connection
     *   Configure your first OPC UA client

2.   **Create Your First Tags**: 
     *   Navigate to the [Tags Module](Tags/index.md)
     *   Create tags from your OPC UA connections
     *   Configure filters and anomaly detection

3.   **Set Up Alarms**: 
     *   Visit the [Alarms Module](Alarms/index.md)
     *   Define alarm conditions for critical process variables
     *   Configure alarm priorities and classifications

4.   **Visualize Your Data**: 
     *   Explore [Real-Time Trends](RealTimeTrends/index.md) for live monitoring
     *   Create custom dashboards with multiple strip charts
     *   Configure buffer sizes for optimal performance

5.   **Monitor and Maintain**: 
     *   Use the [Events Module](Events/index.md) for system audit trails
     *   Create [Operational Logs](OperationalLogs/index.md) for documentation
     *   Monitor [Machines](Machines/index.md) for system health

## Why Choose PyAutomation 2.0.0?

*   **Modern Interface**: React-based UI provides a smooth, responsive experience
*   **Comprehensive**: All-in-one solution for industrial automation
*   **Standards-Compliant**: Follows ISA-18.2 for alarm management
*   **Flexible**: Modular architecture allows customization to your needs
*   **Scalable**: Handles small to enterprise-level deployments
*   **Open Standards**: OPC UA for seamless integration
*   **Well-Documented**: Extensive guides and examples

## Next Steps

Dive deeper into each module by clicking on the links above. Each module guide includes:

*   Detailed feature explanations
*   Step-by-step procedures
*   Visual guides with screenshots
*   Best practices and recommendations
*   Troubleshooting tips
*   Integration examples

**Welcome to PyAutomation 2.0.0 - Where Industrial Automation Meets Modern Web Technology!**
