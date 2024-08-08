from automation.utils.units import *

class Power(EngUnit):
    """Creates a power object that can store a power value and 
    convert between units of power."""

    class Units(UnitSerializer):
        kW = 'kW'
        BTU_hr = 'BTU/hr'
        BTU_min = 'BTU/min'
        BTU_sec = 'BTU/sec'
        cal_sec = 'cal/sec'
        cal_min = 'cal/min'
        cal_hr = 'cal/hr'
        erg_sec = 'erg/sec'
        erg_min = 'erg/min'
        erg_hr = 'erg/hr'
        ftlb_sec = 'ftlb/sec'
        GW = 'GW'
        MW = 'MW'
        kCal_sec = 'kCal/sec'
        kCal_min = 'kCal/min'
        kCal_hr = 'kCal/hr'
        mW = 'mW'
        W = 'W'
        VA = 'VA'
        hp_mech = 'hp_mech'
        hp_ele = 'hp_ele'
        hp_metric = 'hp_metric'
        metric_ton_ref = 'metric_ton_ref'
        US_ton_ref = 'US_ton_ref'
        J_sec = 'J/sec'
        J_min = 'J/min'
        J_hr = 'J/hr'
        kgfm_sec = 'kgf-m/sec'

    conversions = {
        'kW' : 1.0,
        'BTU/hr' : 3412.14,
        'BTU/min' : 56.869,
        'BTU/sec' : 0.94781666666,
        'cal/sec' : 238.85,
        'cal/min' : 238.85 * 60,
        'cal/hr' : 238.85 * 60 * 60,
        'erg/sec' : 10e9,
        'erg/min' : 10e9 * 60,
        'erg/hr' : 10e9 * 60 * 60,
        'ftlb/sec' : 737.56,
        'GW' : 1e-6,
        'MW' : 1e-3,
        'kCal/sec' : 0.24,
        'kCal/min' : 0.24 * 60,
        'kCal/hr' : 0.24 * 60 * 60,
        'mW' : 1e6,
        'W' : 1e3,
        'VA' : 1e3,
        'hp_mech' : 1.3410220888,
        'hp_ele' : 1.3404825737,
        'hp_metric' : 1.359621617304,
        'metric_ton_ref' : 0.259,
        'US_ton_ref' : 0.2843451361,
        'J/sec' : 1000.0,
        'J/min' : 1000.0 * 60,
        'J/hr' : 1000.0 * 60 * 60,
        'kgf-m/sec' : 101.97162129779
    }

    def __init__(self, value, unit):

        if unit not in Power.Units.list():

            raise UnitError(f"{unit} value is not allowed for {self.__class__.__name__} object - you can use: {Power.Units.list()}")
        
        super(Power, self).__init__(value=value, unit=unit)