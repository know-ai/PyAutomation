from enum import Enum


ACTIONS = {
    "Normal": ['shelve', 'suppress by design', 'out of service', 'disable'],
    "Unacknowledged": ['acknowledge', 'shelve', 'suppress by design', 'out of service', 'silence', 'disable'],
    "Acknowledged": ['shelve', 'suppress by design', 'out of service', 'disable'],
    "RTN Unacknowledged": ['shelve', 'suppress by design', 'out of service', 'disable'],
    "Shelved": ["reset"],
    "Suppressed By Design": ["unsuppress by design"],
    "Out Of Service": ["return to service"]
}


class States(Enum):
    r"""
    Enumeration of standard alarm states (ISA 18.2).
    """
    NORM = "Normal"
    UNACK = "Unacknowledged"
    ACKED = "Acknowledged"
    RTNUN = "RTN Unacknowledged"
    SHLVD = "Shelved"
    DSUPR = "Suppressed By Design"
    OOSRV = "Out Of Service"


class Status(Enum):
    r"""
    Enumeration of alarm status attributes.
    """
    ACTV = "Active"
    NACTV = "Not Active"
    ANNCTD = "Annunciated"
    NANNCTD = "Not Annunciated"
    OR = "Not Active or Active"
    SUPR = "Suppressed"
    NA = "Not Applicable"
    NORM = "Normal"
    ABNORM = "Abnormal"


class AlarmAttrs:
    r"""
    Defines the attributes and behavior of a specific alarm state.
    """

    def __init__(
        self, 
        mnemonic: str, 
        state: str, 
        process_condition: str,
        alarm_status: str, 
        annunciate_status: str, 
        acknowledge_status: str,
    ):
        self.__mnemonic = mnemonic
        self.__state = state
        self.__process_condition = process_condition
        self.__alarm_status = alarm_status
        self.__annunciate_status = annunciate_status
        self.__acknowledge_status = acknowledge_status

    @property
    def mnemonic(self):
        r"""
        Gets the state mnemonic (e.g., 'UNACK').
        """
        return self.__mnemonic

    @property
    def state(self):
        r"""
        Gets the full state name (e.g., 'Unacknowledged').
        """
        return self.__state
    
    @property
    def process_condition(self):
        r"""
        Gets the process condition (Normal/Abnormal).
        """
        return self.__process_condition

    @property
    def alarm_status(self):
        r"""
        Gets the alarm activity status (Active/Not Active).
        """
        return self.__alarm_status

    @property
    def annunciate_status(self):
        r"""
        Gets the annunciation status (Annunciated/Not Annunciated).
        """
        return self.__annunciate_status

    @property
    def acknowledge_status(self):
        r"""
        Gets the acknowledgment status.
        """
        return self.__acknowledge_status

    def is_acknowledged(self):
        r"""
        Checks if the alarm is in an acknowledged state.

        **Returns:**

        * **bool**: True if acknowledged, False otherwise.
        """

        return self.acknowledge_status == States.ACKED.value

    def serialize(self):
        r"""
        Serializes the state attributes to a dictionary.

        **Returns:**

        * **dict**: State attributes.
        """
        return {
            'mnemonic': self.mnemonic,
            'state': self.state,
            'process_condition': self.process_condition,
            'alarm_status': self.alarm_status,
            'annunciate_status': self.annunciate_status,
            'acknowledge_status': self.acknowledge_status
        }


class AlarmState:
    r"""
    Static definitions of all standard alarm states with their attributes.
    """

    NORM = AlarmAttrs(
        mnemonic=States.NORM.name,
        state=States.NORM.value,
        process_condition=Status.NORM.value,
        alarm_status=Status.NACTV.value,
        annunciate_status=Status.NANNCTD.value,
        acknowledge_status=States.ACKED.value
    )
    UNACK = AlarmAttrs(
        mnemonic=States.UNACK.name,
        state=States.UNACK.value,
        process_condition=Status.ABNORM.value,
        alarm_status=Status.ACTV.value,
        annunciate_status=Status.ANNCTD.value,
        acknowledge_status=States.UNACK.value
    )
    ACKED = AlarmAttrs(
        mnemonic=States.ACKED.name,
        state=States.ACKED.value,
        process_condition=Status.ABNORM.value,
        alarm_status=Status.ACTV.value,
        annunciate_status=Status.ANNCTD.value,
        acknowledge_status=States.ACKED.value
    )
    RTNUN = AlarmAttrs(
        mnemonic=States.RTNUN.name,
        state=States.RTNUN.value,
        process_condition=Status.NORM.value,
        alarm_status=Status.NACTV.value,
        annunciate_status=Status.ANNCTD.value,
        acknowledge_status=States.UNACK.value
    )
    SHLVD = AlarmAttrs(
        mnemonic=States.SHLVD.name,
        state=States.SHLVD.value,
        process_condition=Status.NORM.value,
        alarm_status=Status.OR.value,
        annunciate_status=Status.SUPR.value,
        acknowledge_status=Status.NA.value
    )
    DSUPR = AlarmAttrs(
        mnemonic=States.DSUPR.name,
        state=States.DSUPR.value,
        process_condition=Status.NORM.value,
        alarm_status=Status.OR.value,
        annunciate_status=Status.SUPR.value,
        acknowledge_status=Status.NA.value
    )
    OOSRV = AlarmAttrs(
        mnemonic=States.OOSRV.name,
        state=States.OOSRV.value,
        process_condition=Status.NORM.value,
        alarm_status=Status.OR.value,
        annunciate_status=Status.SUPR.value,
        acknowledge_status=Status.NA.value
    )

    _states = [NORM, UNACK, ACKED, RTNUN, SHLVD, DSUPR, OOSRV]

    @classmethod
    def get_state_by_name(cls, state:str):
        r"""
        Retrieves an AlarmAttrs object by its state name.

        **Parameters:**

        * **state** (str): The name of the state (e.g., 'Normal').

        **Returns:**

        * **AlarmAttrs**: The state attributes object.
        """
        _state = States(state)
        for alarm_state in cls._states:

            if _state==alarm_state:

                return alarm_state
