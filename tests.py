from unittest import TestLoader, TestSuite, TextTestRunner
from automation.tests.test_user import TestUsers
from automation.tests.test_core import TestCore


def suite():
    """
    Documentation here
    wefwefwefffwfeweffewefwef
    """
    tests = list()
    suite = TestSuite()
    tests.append(TestLoader().loadTestsFromTestCase(TestUsers))
    tests.append(TestLoader().loadTestsFromTestCase(TestCore))
    suite = TestSuite(tests)
    return suite


if __name__=='__main__':
    
    runner = TextTestRunner()
    runner.run(suite())
