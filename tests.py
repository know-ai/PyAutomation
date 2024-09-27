from unittest import TestLoader, TestSuite, TextTestRunner
from automation.tests.test_user import TestUsers


def suite():
    r"""
    Documentation here
    """
    tests = list()
    suite = TestSuite()
    tests.append(TestLoader().loadTestsFromTestCase(TestUsers))
    suite = TestSuite(tests)
    return suite


if __name__=='__main__':
    
    runner = TextTestRunner()
    runner.run(suite())
