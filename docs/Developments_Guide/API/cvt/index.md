# CVT (Current Value Table) API

The Current Value Table (CVT) is the real-time in-memory database of PyAutomation. It stores the current state of all process variables (tags).

## Key Concepts

- **Tag**: A single process variable (e.g., Temperature, Pressure).
- **Engine**: The management layer that handles thread-safe access to the data store.
- **Observer Pattern**: The CVT notifies subscribers (like State Machines and Alarms) whenever a tag value changes.

## Usage

```python
from automation import PyAutomation

app = PyAutomation()
app.create_tag(name="TankLevel", unit="m", variable="Length")

# Reading a tag
tag = app.get_tag_by_name("TankLevel")
print(tag.value)
```
