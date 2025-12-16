<div align="center">

# PyAutomation 2.0.0

### Industrial Automation Meets Modern Web Technology

[![Documentation Status](https://readthedocs.org/projects/pyautomation/badge/?version=latest)](https://pyautomation.readthedocs.io/en/latest/?badge=latest)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/release/python-3100/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![OPC UA](https://img.shields.io/badge/OPC--UA-compliant-orange.svg)](https://opcfoundation.org/)
[![ISA-18.2](https://img.shields.io/badge/ISA--18.2-compliant-green.svg)](https://www.isa.org/)

**Empowering Industry 4.0 with Python, React, and Open Standards**

[Features](#-features) • [Quick Start](#-quick-start) • [Documentation](#-documentation) • [Contributing](#-contributing)

</div>

---

## 🚀 What is PyAutomation?

**PyAutomation** is a comprehensive, enterprise-grade Python framework designed for Industrial IoT (IIoT) and Automation projects. Version 2.0.0 introduces a **revolutionary modern React-based web interface** that combines powerful industrial automation capabilities with an exceptional user experience.

PyAutomation serves as the **bridge between Operational Technology (OT) and Information Technology (IT)**, enabling seamless integration of industrial systems with modern web applications and data analytics platforms.

![PyAutomation Dashboard](docs/Users_Guide/images/FirstPageAfterLogin.png)

*PyAutomation 2.0.0 - Modern React-based Human Machine Interface (HMI)*

---

## 💥 The Open Source Revolution

<div align="center">

### 🎯 Enterprise-Grade Features. Zero Cost. Open Source.

**PyAutomation delivers the same industrial automation power as traditional SCADA systems**—monitoring, alarm management, data logging, real-time trends, and more—**completely FREE**.

</div>

### Why Open Source Wins

| Traditional SCADA | PyAutomation |
|-------------------|--------------|
| 💰 Expensive licensing (per-seat, per-tag) | ✅ **FREE forever** |
| 🔒 Proprietary, vendor lock-in | ✅ **Open source, full control** |
| 📈 High initial costs (6-figure investments) | ✅ **Zero upfront costs** |
| 💸 Annual maintenance fees | ✅ **No ongoing fees** |
| 🚫 Limited customization | ✅ **Fully customizable** |

**You get the same power. You get the same reliability. You get the same features. But you pay $0. Forever.**

---

## ✨ Features

### 🎨 Modern Web Interface (v2.0.0)

- **React-Based HMI**: Fast, responsive, and intuitive user experience
- **Real-Time Updates**: Live data visualization without page refreshes
- **Mobile-Friendly**: Responsive design that adapts to different screen sizes
- **Dark/Light Themes**: Customizable interface themes
- **Multi-Language Support**: Internationalization ready

### 🔌 Industrial Connectivity

- **OPC UA Client & Server**: Native support for OPC UA protocol
- **Multi-Connection Support**: Connect to multiple OPC UA servers simultaneously
- **Data Acquisition**: 
  - **DAQ**: Polling-based data collection
  - **DAS**: Event-driven data collection by subscription
- **Node Browser**: Visual exploration of OPC UA address spaces

### 📊 Real-Time Monitoring & Visualization

- **Current Value Table (CVT)**: In-memory real-time database for fast access
- **Real-Time Trends**: Configurable strip charts with multiple tags
- **Custom Dashboards**: Drag-and-drop dashboard customization
- **Historical Trends**: Long-term data visualization and analysis

### 🚨 Alarm Management

- **ISA-18.2 Compliant**: Industry-standard alarm management
- **Multiple Alarm Types**: BOOL, HIGH, LOW, HIGH-HIGH, LOW-LOW
- **State Management**: Complete lifecycle tracking
- **Alarm History**: Comprehensive audit trail
- **Export Capabilities**: CSV export for compliance reporting

### 💾 Data Logging & Persistence

- **Multi-Database Support**: SQLite, PostgreSQL, MySQL
- **Historical Data Logging**: Configurable sampling rates
- **Event Logging**: Complete system event tracking
- **Operational Logs**: Manual log entry for documentation
- **Data Export**: Flexible filtering and export capabilities

### 🔐 Security & User Management

- **Role-Based Access Control (RBAC)**: Admin, Operator, Guest roles
- **Secure Authentication**: Password management and policies
- **User Administration**: Complete user lifecycle management
- **Audit Trails**: Comprehensive activity logging

### ⚙️ State Machines & Concurrency

- **Concurrent Execution**: Run multiple state machines in parallel
- **State Machine Framework**: Define complex control logic
- **Machine Monitoring**: Real-time state machine status
- **Interval Configuration**: Performance tuning capabilities

### 🔧 Extensibility

- **Modular Architecture**: Easy to extend with custom logic
- **RESTful API**: Full API access for integration
- **Custom State Machines**: Build your own automation logic
- **Plugin Support**: Extensible driver and logger system

---

## 🎯 What You Can Do

### 🔍 Monitoring System
Comprehensive real-time monitoring with intuitive dashboards and live data visualization.

### 📊 Real-Time Trends
Advanced strip chart visualization with configurable dashboards and multiple chart support.

### 🚨 Alarm Management
Enterprise-grade alarm management following ISA-18.2 standards.

### 💾 Historical Data Logging
Comprehensive historical data logging for trend analysis and compliance.

### 👥 User Management
Robust user management with role-based access control.

### 🔮 Coming Soon
- **Configurable SCADA Diagram Access**: Customizable SCADA diagram access with visual process flows
- **Role-Based View Access Control**: Granular permissions for dashboard and view access
- **Modbus TCP**: Direct integration with Modbus-enabled devices
- **MQTT**: IoT and cloud connectivity support

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- Docker and Docker Compose (recommended)
- pip and virtualenv (for local setup)

### Option 1: Docker Deployment (Recommended)

1. **Clone the repository:**

```bash
git clone https://github.com/know-ai/PyAutomation.git
cd PyAutomation
```

2. **Create an `.env` file:**

```ini
AUTOMATION_PORT=8050
AUTOMATION_HMI_PORT=3000
AUTOMATION_VERSION=latest
AUTOMATION_OPCUA_SERVER_PORT=53530
AUTOMATION_APP_SECRET_KEY="CHANGE_ME_TO_A_SECURE_RANDOM_VALUE"
AUTOMATION_SUPERUSER_PASSWORD="CHANGE_ME_SUPERUSER_PASSWORD"
```

3. **Create a `docker-compose.yml`:**

```yaml
services:
  automation:
    container_name: "Automation"
    image: "knowai/automation:${AUTOMATION_VERSION:-latest}"
    restart: always
    ports:
      - ${AUTOMATION_PORT:-8050}:${AUTOMATION_PORT:-8050}
      - ${AUTOMATION_HMI_PORT:-3000}:3000
    volumes:
      - automation_db:/app/db
      - automation_logs:/app/logs
    environment:
      AUTOMATION_OPCUA_SERVER_PORT: ${AUTOMATION_OPCUA_SERVER_PORT:-53530}
      AUTOMATION_APP_SECRET_KEY: ${AUTOMATION_APP_SECRET_KEY}
      AUTOMATION_SUPERUSER_PASSWORD: ${AUTOMATION_SUPERUSER_PASSWORD}
    healthcheck:
      test: ["CMD", "python", "/app/healthcheck.py"]
      interval: 15s
      timeout: 10s
      retries: 3

volumes:
  automation_db:
  automation_logs:
```

4. **Start the service:**

```bash
docker-compose --env-file .env up -d
```

5. **Access the HMI:**

Open your browser and navigate to `http://localhost:3000` (or your configured HMI port).

### Option 2: Local Development Setup

1. **Clone the repository:**

```bash
git clone https://github.com/know-ai/PyAutomation.git
cd PyAutomation
```

2. **Create a virtual environment:**

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. **Run the application:**

```bash
./docker-entrypoint.sh
# Or directly:
# python wsgi.py
```

5. **Access the application:**

Open your browser and navigate to `http://localhost:8050`.

---

## 📚 Documentation

Comprehensive documentation is available at **[Read the Docs](https://pyautomation.readthedocs.io/)**.

### Documentation Sections

- **[User Guide](https://pyautomation.readthedocs.io/en/latest/Users_Guide/index.html)**: Complete guide for operators and engineers
  - Tags Management
  - Alarm Configuration
  - Database Setup
  - Real-Time Trends
  - User Management
  - And much more...

- **[Developer Guide](https://pyautomation.readthedocs.io/en/latest/Developments_Guide/index.html)**: For developers and integrators
  - Architecture Overview
  - API Reference
  - State Machine Development
  - Custom Extensions

- **[Quick Start Guide](https://pyautomation.readthedocs.io/en/latest/Users_Guide/QuickStart.html)**: Get up and running quickly with Docker

---

## 🏗️ Architecture

PyAutomation is built on a modular, extensible architecture:

![Core Architecture](docs/img/PyAutomationCore.svg)

### Core Components

- **State Machines**: Concurrent execution engine for automation logic
- **CVT (Current Value Table)**: In-memory real-time database
- **OPC UA Client/Server**: Industrial protocol integration
- **Data Logger**: Historical data persistence
- **Alarm Manager**: ISA-18.2 compliant alarm system
- **Web Server**: React-based HMI with RESTful API

---

## 🎯 Use Cases

### 🏭 Industrial Monitoring
Real-time monitoring of process variables, equipment status, and system health.

### 📊 Process Visualization
Create custom dashboards and strip charts for live process visualization.

### 🚨 Alarm Management
Enterprise-grade alarm handling with complete lifecycle management.

### 📈 Data Analytics
Historical data logging and analysis for process optimization.

### 🔐 Secure Operations
Role-based access control and comprehensive audit trails.

### 🔌 System Integration
OPC UA integration for seamless connectivity with industrial systems.

---

## 🌟 Why Choose PyAutomation?

### Modern Technology Stack
- ✅ React-based interface for exceptional UX
- ✅ Python backend for flexibility and power
- ✅ Open standards (OPC UA, ISA-18.2)
- ✅ Docker-ready for easy deployment

### Enterprise Features
- ✅ Comprehensive monitoring and visualization
- ✅ Industry-standard alarm management
- ✅ Secure user management
- ✅ Reliable data logging
- ✅ Complete audit trails

### Developer Friendly
- ✅ Well-documented with extensive examples
- ✅ Modular architecture for easy extension
- ✅ RESTful API for integration
- ✅ Open source and community-driven

### Cost Effective
- ✅ **FREE forever** - No licensing costs
- ✅ **Open Source** - Full source code access
- ✅ **No Vendor Lock-in** - Complete freedom
- ✅ **Community Support** - Active development

---

## 🤝 Contributing

We welcome contributions! PyAutomation is an open-source project, and we're excited to work with the community.

### How to Contribute

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Commit your changes** (`git commit -m 'Add some amazing feature'`)
4. **Push to the branch** (`git push origin feature/amazing-feature`)
5. **Open a Pull Request**

Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines on:
- Code of conduct
- Development setup
- Coding standards
- Pull request process
- Issue reporting

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

The MIT License means you are free to:
- ✅ Use PyAutomation commercially
- ✅ Modify the source code
- ✅ Distribute your modifications
- ✅ Use privately

---

## 🌐 Community & Support

### Resources

- 📖 **[Full Documentation](https://pyautomation.readthedocs.io/)**: Comprehensive guides and API reference
- 🐛 **[Issue Tracker](https://github.com/know-ai/PyAutomation/issues)**: Report bugs and request features
- 💬 **[Discussions](https://github.com/know-ai/PyAutomation/discussions)**: Ask questions and share ideas
- 📧 **Contact**: Reach out through GitHub issues or discussions

### Stay Updated

- ⭐ **Star this repository** to stay updated on new releases
- 🔔 **Watch the repository** for notifications
- 📢 **Follow our releases** for the latest features

---

## 🎉 Acknowledgments

PyAutomation is made possible by:

- The **open-source community** and contributors
- **Industry standards** (OPC UA, ISA-18.2) for interoperability
- **Modern web technologies** (React, Python, Docker) for innovation
- **Users and feedback** that drive continuous improvement

---

<div align="center">

## 🚀 Ready to Transform Your Industrial Automation?

**Start your journey with PyAutomation 2.0.0 today**

*Experience the power of modern industrial automation with a world-class user interface*

[![Get Started](https://img.shields.io/badge/Get%20Started-Documentation-blue)](https://pyautomation.readthedocs.io/)
[![Quick Start](https://img.shields.io/badge/Quick%20Start-Docker-green)](https://pyautomation.readthedocs.io/en/latest/Users_Guide/QuickStart.html)

**Welcome to PyAutomation 2.0.0 - Where Industrial Excellence Meets Modern Innovation!**

Made with ❤️ by the PyAutomation Team

</div>
