import logging
import pytz
from peewee import (
    BooleanField,
    CharField,
    TimestampField,
    ForeignKeyField,
    fn,
)
from ..dbmodels.core import BaseModel
from datetime import datetime
from .users import Users
from .events import Events
from .alarms import AlarmSummary, Alarms
from ..modules.users.users import User
from ..utils.operational_log_audit import (
    clip_area,
    clip_description,
    clip_message,
    clip_user_name,
    normalize_shift,
)

DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"


class Logs(BaseModel):
    r"""
    Operator logbook (bitácora) plus comments linked to events or alarm summaries.

    The operator's voice is preserved if a user, event or alarm row is deleted
    (SET NULL + denormalized ``user_name``).
    """

    timestamp = TimestampField(utc=True)
    message = CharField(max_length=256)
    description = CharField(max_length=256, null=True)
    classification = CharField(max_length=128, null=True)
    user = ForeignKeyField(Users, backref='logs', null=True, on_delete='SET NULL')
    user_name = CharField(max_length=64, null=True)
    alarm = ForeignKeyField(AlarmSummary, null=True, backref='logs', on_delete='SET NULL')
    event = ForeignKeyField(Events, null=True, backref='logs', on_delete='SET NULL')
    shift = CharField(max_length=32, null=True)
    area = CharField(max_length=64, null=True, index=True)
    handover = BooleanField(default=False)

    class Meta:
        indexes = (
            (('timestamp',), False),
            (('classification',), False),
            (('area', 'timestamp'), False),
        )

    @classmethod
    def create(
        cls,
        message: str,
        user: User = None,
        description: str = None,
        classification: str = None,
        alarm_summary_id: int = None,
        event_id: int = None,
        timestamp: datetime = None,
        user_name: str = None,
        shift: str = None,
        area: str = None,
        handover: bool = False,
        )->tuple:
        r"""
        Creates a new logbook row. ``user`` may be omitted on SAF replay if
        ``user_name`` is present (author already denormalized).
        """
        author = clip_user_name(
            user_name or (getattr(user, "username", None) if user is not None else None)
        )
        _user = None
        if user is not None:
            if not isinstance(user, User):
                return None, f"User {user} - {type(user)} must be an User Object"
            try:
                from ..catalog.ensure_historian import resolve_historian_user_row

                _user = resolve_historian_user_row(user)
            except Exception:
                _user = None
            author = clip_user_name(user.username) or author

        if not author:
            return None, "user_name is required"

        if not timestamp:
            timestamp = datetime.now(pytz.UTC)

        if not isinstance(timestamp, datetime):
            return None, f"Timestamp must be a datetime Object"

        if timestamp.tzinfo is None:
            timestamp = pytz.UTC.localize(timestamp)
        else:
            timestamp = timestamp.astimezone(pytz.UTC)

        query = cls(
            message=clip_message(message),
            user=_user,
            user_name=author,
            description=clip_description(description),
            classification=clip_message(classification) if classification else None,
            timestamp=timestamp,
            event=Events.get_or_none(id=event_id) if event_id not in (None, "") else None,
            alarm=AlarmSummary.get_or_none(id=alarm_summary_id) if alarm_summary_id not in (None, "") else None,
            shift=normalize_shift(shift),
            area=clip_area(area),
            handover=bool(handover),
        )
        query.save()

        return query, "Log creation successful"

    @classmethod
    def read_lasts(cls, lasts:int=1, area:str=None):
        logs = cls.select()
        if area is not None:
            logs = logs.where(cls.area == area)
        logs = logs.order_by(cls.id.desc()).limit(lasts)
        return [log.serialize() for log in logs]

    @classmethod
    def filter_by(
        cls,
        usernames:list[str]=None,
        alarm_names:list[str]=None,
        event_ids:list[int]=None,
        description:str="",
        message:str="",
        classification:str="",
        classifications:list[str]=None,
        search:str="",
        exclude_description:str="",
        greater_than_timestamp:datetime=None,
        less_than_timestamp:datetime=None,
        timezone:str='UTC',
        page:int=1,
        limit:int=20,
        area:str=None,
        ):
        import math
        _timezone = pytz.timezone(timezone)
        query = cls.select()
        if area is not None:
            query = query.where(cls.area == area)

        if usernames:
            subquery = Users.select(Users.id).where(Users.username.in_(usernames))
            query = query.where(
                (cls.user.in_(subquery)) | (cls.user_name.in_(usernames))
            )

        if event_ids:
            query = query.where(cls.event.in_(event_ids))

        if alarm_names:
            subquery = Alarms.select(Alarms.id).where(Alarms.name.in_(alarm_names))
            alarm_subquery = AlarmSummary.select(AlarmSummary.id).join(Alarms).where(Alarms.id.in_(subquery))
            query = query.where(cls.alarm.in_(alarm_subquery))

        families = [item.lower() for item in (classifications or []) if item]
        if classification and not families:
            query = query.where(fn.LOWER(cls.classification).contains(classification.lower()))
        elif families:
            query = query.where(fn.LOWER(cls.classification).in_(families))

        if search:
            term = search.lower()
            query = query.where(
                fn.LOWER(cls.message).contains(term)
                | fn.LOWER(cls.description).contains(term)
            )
        else:
            if description:
                query = query.where(fn.LOWER(cls.description).contains(description.lower()))
            if message:
                query = query.where(fn.LOWER(cls.message).contains(message.lower()))

        if exclude_description:
            excluded = exclude_description.lower()
            query = query.where(
                cls.description.is_null(True)
                | (fn.LOWER(cls.description) != excluded)
            )

        if greater_than_timestamp:
            greater_than_timestamp = _naive_utc(greater_than_timestamp, _timezone)
            query = query.where(cls.timestamp > greater_than_timestamp)

        if less_than_timestamp:
            less_than_timestamp = _naive_utc(less_than_timestamp, _timezone)
            query = query.where(cls.timestamp < less_than_timestamp)

        query = query.order_by(cls.id.desc())
        total_records = query.count()

        if limit <= 0:
            limit = 20
        if page <= 0:
            page = 1

        total_pages = math.ceil(total_records / limit) if total_records else 1
        has_next = page < total_pages
        has_prev = page > 1
        paginated_query = query.paginate(page, limit)
        data = [log.serialize(timezone=timezone) for log in paginated_query]

        return {
            "data": data,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_records": total_records,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev
            }
        }

    def serialize(self, timezone=None)-> dict:
        from .. import MANUFACTURER, SEGMENT, TIMEZONE
        timestamp = self.timestamp
        if timestamp:
            target_tz = pytz.timezone(timezone) if timezone else TIMEZONE
            if timestamp.tzinfo is None:
                timestamp = pytz.UTC.localize(timestamp)
            timestamp = timestamp.astimezone(target_tz)
            timestamp = timestamp.strftime(DATETIME_FORMAT)

        username = self.user_name
        user_payload = {"username": username} if username else None
        if self.user:
            user_payload = self.user.serialize()
            if username and not user_payload.get("username"):
                user_payload["username"] = username

        _event = self.event.serialize() if self.event else None
        _alarm = self.alarm.serialize() if self.alarm else None

        return {
            "id": self.id,
            "timestamp": timestamp,
            "user": user_payload,
            "user_name": username,
            "message": self.message,
            "description": self.description,
            "classification": self.classification,
            "shift": self.shift,
            "area": self.area,
            "handover": bool(self.handover),
            "event": _event,
            "alarm": _alarm,
            "segment": SEGMENT,
            "manufacturer": MANUFACTURER
        }

    @classmethod
    def ensure_schema(cls) -> None:
        """Add Bitácora Eterna columns and SET NULL FKs on existing historians."""
        database = cls._meta.database
        if database is None:
            return
        table = cls._meta.table_name
        logger = logging.getLogger("pyautomation")
        dialect = type(database).__name__.lower()
        try:
            columns = {column.name for column in database.get_columns(table)}
        except Exception:
            logger.warning("Logs schema inspect skipped for %s", table, exc_info=True)
            return

        additions = (
            ("user_name", "VARCHAR(64)"),
            ("shift", "VARCHAR(32)"),
            ("area", "VARCHAR(64)"),
            ("handover", "INTEGER DEFAULT 0" if "sqlite" in dialect else "BOOLEAN DEFAULT FALSE"),
        )
        for name, ddl in additions:
            if name in columns:
                continue
            try:
                database.execute_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                logger.info("Logs: added column %s.%s", table, name)
            except Exception:
                logger.warning("Logs: add column %s skipped", name, exc_info=True)

        try:
            database.execute_sql(
                f"UPDATE {table} SET user_name = ("
                f"SELECT username FROM {Users._meta.table_name} "
                f"WHERE {Users._meta.table_name}.id = {table}.user_id"
                f") WHERE user_name IS NULL AND user_id IS NOT NULL"
            )
        except Exception:
            logger.debug("Logs: backfill user_name skipped", exc_info=True)

        try:
            database.execute_sql(
                f"CREATE INDEX IF NOT EXISTS {table}_timestamp ON {table} (timestamp)"
            )
        except Exception:
            logger.debug("Logs: timestamp index skipped", exc_info=True)

        if "postgres" in dialect:
            _ensure_postgres_set_null_fks(database, table, logger)


def _naive_utc(value, timezone):
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(pytz.UTC).replace(tzinfo=None)
        return value
    try:
        raw = str(value)
        if '.' in raw:
            parts = raw.split('.')
            microseconds = (parts[1] if len(parts) > 1 else '0').ljust(6, '0')[:6]
            dt_naive = datetime.strptime(f"{parts[0]}.{microseconds}", '%Y-%m-%d %H:%M:%S.%f')
        else:
            dt_naive = datetime.strptime(raw, '%Y-%m-%d %H:%M:%S')
        return timezone.localize(dt_naive).astimezone(pytz.UTC).replace(tzinfo=None)
    except ValueError:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if dt.tzinfo is not None:
            dt = dt.astimezone(pytz.UTC)
        return dt.replace(tzinfo=None)


def _ensure_postgres_set_null_fks(database, table: str, logger) -> None:
    try:
        database.execute_sql(f"ALTER TABLE {table} ALTER COLUMN user_id DROP NOT NULL")
    except Exception:
        logger.debug("Logs: user_id already nullable", exc_info=True)

    try:
        rows = database.execute_sql(
            f"SELECT conname FROM pg_constraint "
            f"WHERE conrelid = '{table}'::regclass AND contype = 'f'"
        )
        names = [row[0] for row in rows]
    except Exception:
        logger.warning("Logs: list FK constraints skipped", exc_info=True)
        return

    for name in names:
        try:
            database.execute_sql(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{name}"')
        except Exception:
            logger.warning("Logs: drop FK %s skipped", name, exc_info=True)

    statements = (
        f"ALTER TABLE {table} ADD CONSTRAINT {table}_user_id_fkey "
        f"FOREIGN KEY (user_id) REFERENCES {Users._meta.table_name}(id) ON DELETE SET NULL",
        f"ALTER TABLE {table} ADD CONSTRAINT {table}_event_id_fkey "
        f"FOREIGN KEY (event_id) REFERENCES {Events._meta.table_name}(id) ON DELETE SET NULL",
        f"ALTER TABLE {table} ADD CONSTRAINT {table}_alarm_id_fkey "
        f"FOREIGN KEY (alarm_id) REFERENCES {AlarmSummary._meta.table_name}(id) ON DELETE SET NULL",
    )
    for sql in statements:
        try:
            database.execute_sql(sql)
        except Exception:
            logger.debug("Logs: add SET NULL FK skipped (%s)", sql, exc_info=True)
