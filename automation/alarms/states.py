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


# Canonical names persisted in alarm_summary.from_state / to_state (SPEC-ISA18-2-P0P1 §3.1).
HISTORY_NORMAL = "Normal"
HISTORY_UNACK = "Unack Alarm"
HISTORY_ACK = "Ack Alarm"
HISTORY_RTNUN = "RTN Unack"
HISTORY_CLEARED = "Cleared"
HISTORY_SHELVED = "Shelved"
HISTORY_DSUPR = "Suppressed By Design"
HISTORY_OOSRV = "Out Of Service"

HISTORY_SUPPRESSED = frozenset({HISTORY_SHELVED, HISTORY_DSUPR, HISTORY_OOSRV})
HISTORY_ANNUNCIATED = frozenset({HISTORY_UNACK, HISTORY_ACK, HISTORY_RTNUN})
ACKABLE_HISTORY = frozenset({HISTORY_UNACK, HISTORY_ACK, HISTORY_RTNUN})

_SM_TO_HISTORY = {
    "normal": HISTORY_NORMAL,
    "unack_alarm": HISTORY_UNACK,
    "ack_alarm": HISTORY_ACK,
    "rtn_unack": HISTORY_RTNUN,
    "shelved": HISTORY_SHELVED,
    "suppressed_by_design": HISTORY_DSUPR,
    "out_of_service": HISTORY_OOSRV,
}

_ISA_TO_HISTORY = {
    "Normal": HISTORY_NORMAL,
    "Unacknowledged": HISTORY_UNACK,
    "Acknowledged": HISTORY_ACK,
    "RTN Unacknowledged": HISTORY_RTNUN,
    "Shelved": HISTORY_SHELVED,
    "Suppressed By Design": HISTORY_DSUPR,
    "Out Of Service": HISTORY_OOSRV,
    HISTORY_UNACK: HISTORY_UNACK,
    HISTORY_ACK: HISTORY_ACK,
    HISTORY_RTNUN: HISTORY_RTNUN,
    HISTORY_CLEARED: HISTORY_CLEARED,
}

_HISTORY_TO_ISA = {
    HISTORY_NORMAL: "Normal",
    HISTORY_UNACK: "Unacknowledged",
    HISTORY_ACK: "Acknowledged",
    HISTORY_RTNUN: "RTN Unacknowledged",
    HISTORY_CLEARED: "Normal",
    HISTORY_SHELVED: "Shelved",
    HISTORY_DSUPR: "Suppressed By Design",
    HISTORY_OOSRV: "Out Of Service",
}

_HISTORY_TO_SM = {
    HISTORY_NORMAL: "normal",
    HISTORY_UNACK: "unack_alarm",
    HISTORY_ACK: "ack_alarm",
    HISTORY_RTNUN: "rtn_unack",
    HISTORY_CLEARED: "normal",
    HISTORY_SHELVED: "shelved",
    HISTORY_DSUPR: "suppressed_by_design",
    HISTORY_OOSRV: "out_of_service",
}


def history_name_from_sm(sm_name: str | None) -> str:
    if not sm_name:
        return HISTORY_NORMAL
    return _SM_TO_HISTORY.get(str(sm_name).lower(), HISTORY_NORMAL)


def history_name_from_isa(name: str | None) -> str:
    if not name:
        return HISTORY_NORMAL
    return _ISA_TO_HISTORY.get(str(name), str(name))


def isa_name_from_history(name: str | None) -> str:
    if not name:
        return "Normal"
    return _HISTORY_TO_ISA.get(str(name), str(name))


def sm_value_from_history(name: str | None) -> str:
    if not name:
        return "normal"
    return _HISTORY_TO_SM.get(str(name), "normal")


def sm_value_from_isa(name: str | None) -> str:
    return sm_value_from_history(history_name_from_isa(name))


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
