# Project Roadmap

This document outlines the development roadmap for PyAutomation, detailing current features, upcoming releases, and long-term goals to establish it as a world-class industrial automation platform.

## 🚀 Vision

To build a robust, scalable, and secure open-source Industrial IoT (IIoT) and SCADA platform that bridges the gap between traditional OT (Operational Technology) and modern IT (Information Technology).

---

## 📅 Upcoming Releases

### v1.2.0 - Connectivity & Performance (Short Term)

Focus on expanding industrial protocols and modernizing the core stack.

- [ ] **Industrial Protocols**
  - [ ] Modbus TCP (Client - Server) implementation.
  - [ ] OPC DA (Client - Server) legacy support.
- [ ] **Instrument Anomaly Detection (IAD)**
  - [ ] Sensor Drift detection algorithms.
- [ ] **Architecture Modernization**
  - [ ] Migrate backend from Flask to **FastAPI** for high-performance async operations.
  - [ ] Migrate Configuration UI from Dash to **React** for a more responsive user experience.

### v2.0.0 - IIoT & Security (Medium Term)

Focus on IoT standards, security compliance, and containerization.

- [ ] **IIoT Connectivity**
  - [ ] **MQTT Support**: Implementation of MQTT v5 and **Sparkplug B** specification for standard IIoT communication.
- [ ] **Advanced Security**
  - [ ] **RBAC (Role-Based Access Control)**: Granular permissions for Users, Operators, and Admins.
  - [ ] **JWT Authentication**: Secure, stateless API authentication.
  - [ ] **Audit Trails**: FDA 21 CFR Part 11 compliant logging of all user actions and setpoint changes.
- [ ] **Deployment & Scalability**
  - [ ] **Docker & Kubernetes**: Official Helm charts and optimized Docker images.
  - [ ] **Health Checks**: Native endpoints for liveness/readiness probes.

### v3.0.0 - Enterprise Features (Long Term)

Focus on high availability, cloud integration, and advanced analytics.

- [ ] **High Availability (HA)**
  - [ ] Active/Passive redundancy clustering.
  - [ ] Automatic failover mechanisms.
- [ ] **Cloud Integration**
  - [ ] Native connectors for **AWS IoT Core** and **Azure IoT Hub**.
- [ ] **Reporting & Analytics**
  - [ ] Automated PDF/Excel report generation.
  - [ ] Advanced historical trending with data export.
- [ ] **Logic Engine**
  - [ ] User-defined Python scripts (SoftPLC functionality) safely sandboxed.

---

## ✅ Completed Features (v1.1.5)

### Core Systems

- [x] **State Machines**: Synchronous and Asynchronous implementation.
- [x] **CVT (Current Value Table)**: In-memory tag repository for high-speed access.
- [x] **Alarm Management**: Full lifecycle management (Trigger, Acknowledge, Clear).
- [x] **Data Logger**: Robust data persistency engines.
- [x] **Workers**: Dedicated thread/process workers for DataLogger, Alarms, and State Machines.
- [x] **Engines**: Thread-safe mechanisms for CVT, DataLogger, and Alarms.

### Data & Models

- [x] **DB Models**: comprehensive ORM models for Alarms, Tags, Machines, Users, and Logs.
- [x] **Data Filtering**: Real-time signal conditioning.
- [x] **Anomaly Detection**:
  - [x] Outliers detection.
  - [x] Out of Range validation.
  - [x] Frozen Data detection.

### Connectivity

- [x] **OPC UA**: Full Client & Server implementation.
