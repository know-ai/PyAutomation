from unittest import TestLoader, TestSuite, TextTestRunner
from automation.tests.test_user import TestUsers
from automation.tests.test_core import TestCore
from automation.tests.test_unit import TestConversions
from automation.tests.test_alarms import TestAlarms


def suite():
    """
    Documentation here
    wefwefwefffwfeweffewefwef
    """
    tests = list()
    suite = TestSuite()
    tests.append(TestLoader().loadTestsFromTestCase(TestConversions))
    tests.append(TestLoader().loadTestsFromTestCase(TestUsers))
    tests.append(TestLoader().loadTestsFromTestCase(TestCore))
    tests.append(TestLoader().loadTestsFromTestCase(TestAlarms))
    suite = TestSuite(tests)
    return suite


if __name__=='__main__':
    
    runner = TextTestRunner()
    runner.run(suite())
