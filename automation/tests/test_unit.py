import unittest
from ..variables import (Pressure)

class TestConversions(unittest.TestCase):

    def setUp(self) -> None:
        
        return super().setUp()

    def tearDown(self) -> None:
        
        return super().tearDown()
    
    def test_pressure_conversions(self):

        value = 10
        from_unit = "atm"
        to_unit = "psi"
        expected = 146.959

        self.assertAlmostEqual(Pressure.convert_value(value, from_unit=from_unit, to_unit=to_unit), expected, delta=0.001)
