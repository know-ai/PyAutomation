# PyAutomation Testing

<div align="center" style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 15px; padding: 3em 2em; margin: 2em 0; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">

<h2 style="color: #1b5e20; font-size: 2.5em; margin-bottom: 0.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.1); font-weight: 700;">
  ✅ Comprehensive Test Suite
</h2>

<p style="color: #0d4f1c; font-size: 1.4em; margin-top: 1em; font-weight: 500;">
  PyAutomation maintains a comprehensive suite of unit and integration tests to ensure stability and reliability. We use <code>pytest</code> as our testing framework.
</p>

</div>

## Test Structure

<div style="background: #f8f9fa; border-left: 5px solid #4caf50; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
Tests are located in the <code>automation/tests/</code> directory.
</p>

<ul style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><code>test_core.py</code>: Tests the core <code>PyAutomation</code> singleton, app initialization, and configuration.</li>
<li><code>test_alarms.py</code>: Validates alarm creation, triggering, and state transitions.</li>
<li><code>test_unit.py</code>: Tests unit conversion logic and variable types.</li>
<li><code>test_user.py</code>: Tests user management, authentication (login/signup), and role handling.</li>
</ul>

</div>

## Running Tests

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 2em 0; border: 2px solid #4caf50;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
To run the full test suite, navigate to the project root and run:
</p>

```bash
pytest
```

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 1.5em 0 1em 0; font-weight: 500;">
To run a specific test file:
</p>

```bash
pytest automation/tests/test_core.py
```

### Coverage

<div style="background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; border: 2px solid #2196f3;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
We strive for high code coverage. You can check coverage using <code>pytest-cov</code>:
</p>

```bash
pytest --cov=automation
```

</div>

</div>

---

## Writing Tests

<div style="background: #f8f9fa; border-left: 5px solid #4caf50; padding: 1.5em; margin: 2em 0; border-radius: 5px;">

<p style="color: #1a202c; font-size: 1.1em; line-height: 1.8; margin: 0 0 1em 0; font-weight: 500;">
When contributing new features, please add corresponding tests. Follow these guidelines:
</p>

<ol style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; padding-left: 1.5em; font-weight: 400;">
<li><strong>Isolation</strong>: Use the test database (<code>test.db</code>) to avoid affecting production data. The <code>PyAutomation</code> class supports a <code>test=True</code> parameter in <code>connect_to_db</code> for this purpose.</li>
<li><strong>Fixtures</strong>: Use <code>pytest</code> fixtures for setup and teardown (e.g., creating a temporary app instance).</li>
<li><strong>Assertions</strong>: Write clear assertions for expected outcomes.</li>
</ol>

</div>

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

---

## Continuous Integration

<div style="background: #e8f5e9; border-radius: 8px; padding: 1.5em; margin: 2em 0; border: 2px solid #4caf50;">

<p style="color: #1a202c; font-size: 1em; line-height: 1.8; margin: 0; font-weight: 400;">
Tests are automatically executed on GitHub Actions for every push and pull request to the <code>dev</code> and <code>main</code> branches. Ensure all tests pass locally before submitting changes.
</p>

</div>
