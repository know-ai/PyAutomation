# PyAutomation Core API

The `PyAutomation` class is the central entry point for the framework. It implements the Singleton pattern to ensure a unified control point for all services (Tags, Alarms, Database, Workers).

## Usage

```python
from automation import PyAutomation

app = PyAutomation()
app.run(debug=True)
```

## Class Documentation

::: automation.PyAutomation
    :docstring:
    :members:
