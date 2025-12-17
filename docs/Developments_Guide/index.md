# Developer's Guide

<div align="center" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 15px; padding: 3em 2em; margin: 2em 0; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">

<h2 style="color: white; font-size: 2.5em; margin-bottom: 0.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); font-weight: 700;">
  👨‍💻 Build, Extend, and Integrate
</h2>

<p style="color: white; font-size: 1.4em; margin-top: 1em; font-weight: 500; opacity: 0.95;">
  Welcome to the PyAutomation Developer's Guide. This section is designed for software engineers and integrators who want to extend the framework, create custom state machines, or integrate PyAutomation with other systems.
</p>

</div>

## Content Overview

<div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); border-radius: 10px; padding: 2em; margin: 2em 0; border: 2px solid #2196f3;">

<ul style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong><a href="standards.md" style="color: #1976d2; font-weight: 600;">Industrial Standards</a></strong>: Comprehensive overview of industrial standards implementation, compliance status, and roadmap.</li>
<li><strong><a href="architecture_components.md" style="color: #1976d2; font-weight: 600;">Architecture Components</a></strong>: Technical explanation of Workers, Engines, and Managers - the three fundamental architectural components.</li>
<li><strong><a href="API/index.md" style="color: #1976d2; font-weight: 600;">API Reference</a></strong>: Detailed documentation of the core classes, methods, and modules.</li>
<li><strong><a href="../architecture.md" style="color: #1976d2; font-weight: 600;">Core Architecture</a></strong>: Deep dive into the internal design and data flow.</li>
<li><strong><a href="API/state_machine/index.md" style="color: #1976d2; font-weight: 600;">State Machines</a></strong>: How to implement custom logic using the State Machine engine.</li>
<li><strong><a href="API/cvt/index.md" style="color: #1976d2; font-weight: 600;">CVT (Current Value Table)</a></strong>: Interacting with the real-time data store.</li>
<li><strong><a href="API/managers/index.md" style="color: #1976d2; font-weight: 600;">Database Managers</a></strong>: Understanding data persistence layers.</li>
</ul>

</div>

---

## Development Environment Setup

<div style="background: #f8f9fa; border-left: 5px solid #2196f3; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 500;">
To start developing, ensure you have set up your local environment as described in the <a href="../setup.md" style="color: #1976d2; font-weight: 600;">Setup</a> guide.
</p>

</div>

### Running Tests

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #4caf50;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
We encourage writing tests for new features. PyAutomation uses <code>pytest</code>.
</p>

```bash
pytest
```

</div>

---

## Contributing

<div style="background: #f8f9fa; border-left: 5px solid #9c27b0; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0; font-weight: 500;">
Please refer to <a href="../CONTRIBUTING.md" style="color: #7b1fa2; font-weight: 600;">CONTRIBUTING.md</a> in the documentation root for guidelines on code style, pull requests, and commit messages.
</p>

</div>
