import doctest
import os
from unittest import TestLoader, TestSuite, TextTestRunner

# En tests/doctests evitamos output a stdout desde automation/core.py (prints coloreados),
# porque rompe las aserciones de doctest ("Expected nothing").
os.environ.setdefault("AUTOMATION_CONSOLE_LOGS", "0")

from automation.tests.test_user import TestUsers
from automation.tests.test_core import TestCore
from automation.tests.test_unit import TestConversions
from automation.tests.test_alarms import TestAlarms
from automation.utils import units
from automation.variables import (
    volumetric_flow,
    pressure,
    mass_flow,
    density,
    length,
    mass,
    power,
    force,
    current,
    eng_time,
    temperature,
    volume
)
from automation import core, PyAutomation, server
app = PyAutomation()
setattr(app, "server", server)

def suite():
    """
    Documentation here
    """
    tests = list()
    suite = TestSuite()
    tests.append(TestLoader().loadTestsFromTestCase(TestConversions))
    tests.append(TestLoader().loadTestsFromTestCase(TestUsers))
    tests.append(TestLoader().loadTestsFromTestCase(TestCore))
    tests.append(TestLoader().loadTestsFromTestCase(TestAlarms))
    # DOCTESTS
    doctests = list()
    doctests.append(units)
    doctests.append(volumetric_flow)
    doctests.append(volume)
    doctests.append(pressure)
    doctests.append(mass_flow)
    doctests.append(density)
    doctests.append(length)
    doctests.append(mass)
    doctests.append(power)
    doctests.append(force)
    doctests.append(current)
    doctests.append(eng_time)
    doctests.append(temperature)
    doctests.append(core)

    suite = TestSuite(tests)
    return suite, doctests


if __name__=='__main__':
    import sys
    runner = TextTestRunner()
    unittests, doctests = suite()

    try:
        result = runner.run(unittests)
        # Importante: algunos tests/unit tests pueden dejar threads/tareas en background
        # que siguen imprimiendo logs a stdout. Eso rompe los doctests (capturan stdout).
        # Detenemos la app antes de ejecutar doctests para evitar "ruido" no determinista.
        app.safe_stop()
        
        doctest_failures = 0
        for _doctest in doctests:
            res = doctest.testmod(_doctest, verbose=False)
            doctest_failures += res.failed

        if not result.wasSuccessful() or doctest_failures > 0:
            sys.exit(1)
    
    finally:
        # Force stop of any background threads started during doctests
        app.safe_stop()
