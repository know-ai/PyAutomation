from ..utils.units import EngUnit, UnitSerializer, UnitError


class DataSize(EngUnit):
    """Binary data size. The base factor is the byte; MB is 1024×1024 bytes."""

    class Units(UnitSerializer):
        B = "B"
        kB = "kB"
        MB = "MB"
        GB = "GB"

    conversions = {
        "B": 1.0,
        "kB": 1.0 / 1024.0,
        "MB": 1.0 / 1024.0 / 1024.0,
        "GB": 1.0 / 1024.0 / 1024.0 / 1024.0,
    }

    def __init__(self, value, unit):
        if unit not in DataSize.Units.list():
            raise UnitError(
                f"{unit} value is not allowed for {self.__class__.__name__} object - "
                f"you can use: {DataSize.Units.list()}"
            )
        super(DataSize, self).__init__(value=value, unit=unit)
