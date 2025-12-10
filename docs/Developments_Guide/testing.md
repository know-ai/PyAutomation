# PyAutomation Testing

PyAutomation maintains a comprehensive suite of unit and integration tests to ensure stability and reliability. We use `pytest` as our testing framework.

## Test Structure

Tests are located in the `automation/tests/` directory.

- `test_core.py`: Tests the core `PyAutomation` singleton, app initialization, and configuration.
- `test_alarms.py`: Validates alarm creation, triggering, and state transitions.
- `test_unit.py`: Tests unit conversion logic and variable types.
- `test_user.py`: Tests user management, authentication (login/signup), and role handling.

## Running Tests

To run the full test suite, navigate to the project root and run:

```bash
pytest
```

To run a specific test file:

```bash
pytest automation/tests/test_core.py
```

### Coverage

We strive for high code coverage. You can check coverage using `pytest-cov`:

```bash
pytest --cov=automation
```

## Writing Tests

When contributing new features, please add corresponding tests. Follow these guidelines:

1.  **Isolation**: Use the test database (`test.db`) to avoid affecting production data. The `PyAutomation` class supports a `test=True` parameter in `connect_to_db` for this purpose.
2.  **Fixtures**: Use `pytest` fixtures for setup and teardown (e.g., creating a temporary app instance).
3.  **Assertions**: Write clear assertions for expected outcomes.

### Example Test Case

```python
from automation import PyAutomation

def test_create_tag():
    app = PyAutomation()
    # Connect to test DB
    app.connect_to_db(test=True)

    tag, msg = app.create_tag(name="TestTag", unit="V", variable="Voltage")

    assert tag is not None
    assert tag.name == "TestTag"
    assert app.cvt.get_tag_by_name("TestTag") is not None
```

## Continuous Integration

Tests are automatically executed on GitHub Actions for every push and pull request to the `dev` and `main` branches. Ensure all tests pass locally before submitting changes.
