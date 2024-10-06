import doctest
from unittest import TestLoader, TestSuite, TextTestRunner
from automation.tests.test_user import TestUsers
from automation.tests.test_core import TestCore
from automation.tests.test_unit import TestConversions
from automation.tests.test_alarms import TestAlarms
# from automation.tests.doctests.eng_unit import TestDoctestsEngUnit
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
    temperature
)
from automation import core


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
    
    runner = TextTestRunner()
    unittests, doctests = suite()
    runner.run(unittests)
    for _doctest in doctests:
    
        doctest.testmod(_doctest, verbose=False)
