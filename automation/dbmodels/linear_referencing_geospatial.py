from peewee import ForeignKeyField, FloatField
from .core import BaseModel
from .tags import Segment


class LinearReferencingGeospatial(BaseModel):
    r"""
    Database model for geospatial linear-referencing points of a pipeline segment.
    """

    segment = ForeignKeyField(Segment, backref='linear_referencing_points', on_delete='CASCADE')
    kp = FloatField()
    latitude = FloatField()
    longitude = FloatField()
    elevation = FloatField(null=True)

    class Meta:
        indexes = (
            (('segment', 'kp'), True),
        )

    @classmethod
    def create(
        cls,
        segment_name:str,
        kp:float,
        latitude:float,
        longitude:float,
        elevation:float=None
    ):
        r"""
        Creates a new linear-referencing geospatial point.
        """
        segment_obj = Segment.read_by_name(name=segment_name)
        if segment_obj is None:
            return None, f"Segment {segment_name} does not exist into database"

        duplicated = cls.get_or_none((cls.segment == segment_obj) & (cls.kp == kp))
        if duplicated is not None:
            return None, f"Duplicated linear referencing point: {segment_name} KP {kp}"

        query = cls(
            segment=segment_obj,
            kp=kp,
            latitude=latitude,
            longitude=longitude,
            elevation=elevation
        )
        query.save()
        return query, "Linear referencing geospatial point created successfully"

    @classmethod
    def read_by_segment_name(cls, segment_name:str):
        r"""
        Retrieves all points by segment name ordered by KP ascending.
        """
        segment_obj = Segment.read_by_name(name=segment_name)
        if segment_obj is None:
            return []
        query = cls.select().where(cls.segment == segment_obj).order_by(cls.kp.asc())
        return query

    @classmethod
    def delete_by_id(cls, id:int):
        r"""
        Deletes a point by its numeric ID.
        """
        if not cls.id_exists(id):
            return 0
        query = cls.delete().where(cls.id == id)
        return query.execute()

    @classmethod
    def interpolate_by_segment_and_kp(cls, segment_name:str, kp:float):
        r"""
        Retrieves geospatial data by segment and KP using linear interpolation if needed.
        """
        segment_obj = Segment.read_by_name(name=segment_name)
        if segment_obj is None:
            return None, f"Segment {segment_name} does not exist into database"

        exact = cls.get_or_none((cls.segment == segment_obj) & (cls.kp == kp))
        if exact is not None:
            data = exact.serialize()
            data["interpolated"] = False
            return data, "Exact KP match"

        lower = (
            cls.select()
            .where((cls.segment == segment_obj) & (cls.kp < kp))
            .order_by(cls.kp.desc())
            .first()
        )
        upper = (
            cls.select()
            .where((cls.segment == segment_obj) & (cls.kp > kp))
            .order_by(cls.kp.asc())
            .first()
        )

        if lower is None and upper is None:
            return None, f"No geospatial points configured for segment {segment_name}"

        if lower is None:
            data = upper.serialize()
            data["requested_kp"] = kp
            data["interpolated"] = False
            data["interpolation_note"] = "Requested KP below available range; nearest upper point returned"
            return data, "Nearest point returned"

        if upper is None:
            data = lower.serialize()
            data["requested_kp"] = kp
            data["interpolated"] = False
            data["interpolation_note"] = "Requested KP above available range; nearest lower point returned"
            return data, "Nearest point returned"

        kp_span = upper.kp - lower.kp
        if kp_span == 0:
            return None, "Invalid interpolation range (duplicated KP points)"

        ratio = (kp - lower.kp) / kp_span
        latitude = lower.latitude + (upper.latitude - lower.latitude) * ratio
        longitude = lower.longitude + (upper.longitude - lower.longitude) * ratio
        elevation = None
        if lower.elevation is not None and upper.elevation is not None:
            elevation = lower.elevation + (upper.elevation - lower.elevation) * ratio

        return {
            "id": None,
            "segment_id": segment_obj.id,
            "segment_name": segment_obj.name,
            "kp": kp,
            "latitude": latitude,
            "longitude": longitude,
            "elevation": elevation,
            "interpolated": True,
            "interpolation_bounds": {
                "lower_kp": lower.kp,
                "upper_kp": upper.kp
            }
        }, "Interpolated KP location"

    def serialize(self):
        r"""
        Serializes the linear-referencing geospatial point.
        """
        return {
            "id": self.id,
            "segment_id": self.segment.id,
            "segment_name": self.segment.name,
            "kp": self.kp,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation": self.elevation
        }
