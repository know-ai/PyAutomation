# Developer's Guide

Welcome to the PyAutomation Developer's Guide. This section is designed for software engineers and integrators who want to extend the framework, create custom state machines, or integrate PyAutomation with other systems.

## Content Overview

- **[Industrial Standards](standards.md)**: Comprehensive overview of industrial standards implementation, compliance status, and roadmap.
- **[API Reference](API/index.md)**: Detailed documentation of the core classes, methods, and modules.
- **[Core Architecture](../architecture.md)**: Deep dive into the internal design and data flow.
- **[State Machines](API/state_machine/index.md)**: How to implement custom logic using the State Machine engine.
- **[CVT (Current Value Table)](API/cvt/index.md)**: Interacting with the real-time data store.
- **[Database Managers](API/managers/index.md)**: Understanding data persistence layers.

## Development Environment Setup

To start developing, ensure you have set up your local environment as described in the [Setup](../setup.md) guide.

### Running Tests

We encourage writing tests for new features. PyAutomation uses `pytest`.

```bash
pytest
```

## Contributing

Please refer to [CONTRIBUTING.md](../CONTRIBUTING.md) in the documentation root for guidelines on code style, pull requests, and commit messages.
