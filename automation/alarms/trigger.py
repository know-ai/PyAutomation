from enum import Enum

class TriggerType(Enum):
    r"""
    Enumeration of alarm trigger types.

    * **HH**: High-High (Critical High)
    * **H**: High
    * **L**: Low
    * **LL**: Low-Low (Critical Low)
    * **B**: Boolean
    * **NONE**: Not Defined
    """
    HH = "HIGH-HIGH"
    H = "HIGH"
    L = "LOW"
    LL = "LOW-LOW"
    B = "BOOL"
    NONE = "NOT DEFINED"


class Trigger:
    r"""
    Represents the condition that triggers an alarm.

    It stores the type of trigger (e.g., HIGH, LOW) and the threshold value.
    """

    def __init__(self):

        self.__type = TriggerType.NONE
        self.__value = None

    @property
    def type(self):
        r"""
        Gets the trigger type.
        """

        return self.__type

    @type.setter
    def type(self, _type:str):
        r"""
        Sets the trigger type.

        **Parameters:**

        * **_type** (str): The trigger type string (e.g., 'HIGH', 'BOOL').
        """
        self.__type = TriggerType(_type)

    @property
    def value(self):
        r"""
        Gets the threshold value.
        """
        return self.__value

    @value.setter
    def value(self, value):
        r"""
        Sets the threshold value.

        Automatically casts the value to `bool` if the trigger type is Boolean,
        otherwise casts to `float` or `int`.

        **Parameters:**

        * **value**: The threshold value.
        """
        if self.type==TriggerType.B:

            if isinstance(value, bool):

                self.__value = value

            else:

                self.__value = bool(value)

        else:

            if isinstance(value, (float, int)):

                self.__value = value

    def serialize(self):
        r"""
        Serializes the trigger object to a dictionary.

        **Returns:**

        * **dict**: {'type': str, 'value': any}
        """
        return {
            "type": self.type.value,
            "value": self.value
        }