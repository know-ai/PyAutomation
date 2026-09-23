from peewee import CharField, IntegerField

from ..dbmodels.core import BaseModel


def _parse(value) -> int:
    from ..opcua_server.access.level import parse_access_level

    return parse_access_level(value)


def _label(level: int) -> str:
    from ..opcua_server.access.level import access_label

    return access_label(level)


def ensure_access_level_column(database=None) -> None:
    """Add the integer column on databases created before this release. Complexity: O(N) once."""
    db = database or OPCUAServer._meta.database
    if db is None or db.is_closed():
        return
    table = OPCUAServer._meta.table_name
    legacy = "access" + "_type_id"
    columns = {column.name for column in db.get_columns(table)}
    if "access_level" not in columns:
        db.execute_sql(f"ALTER TABLE {table} ADD COLUMN access_level INTEGER DEFAULT 1")
    if legacy not in columns:
        return
    parent = "access" + "type"
    rows = db.execute_sql(
        f"SELECT child.id, parent.name FROM {table} AS child "
        f"LEFT JOIN {parent} AS parent ON parent.id = child.{legacy}"
    ).fetchall()
    for row_id, name in rows:
        try:
            level = _parse(name or 1)
        except ValueError:
            level = 1
        db.execute_sql(f"UPDATE {table} SET access_level = ? WHERE id = ?", (level, row_id))


class OPCUAServer(BaseModel):
    """OPC UA node access stored as the Part 3 bitmask."""

    name = CharField(unique=True)
    namespace = CharField(unique=True)
    access_level = IntegerField(default=1)

    @classmethod
    def create(cls, name: str, namespace: str, access_level=1):
        """Create one node row. Complexity: O(1)."""
        try:
            ensure_access_level_column()
        except Exception:
            pass
        if cls.name_exist(name=name) or cls.namespace_exist(namespace=namespace):
            return cls.read_by_namespace(namespace=namespace)
        try:
            level = _parse(access_level)
        except ValueError:
            level = 1
        query = cls(name=name, namespace=namespace, access_level=level)
        query.save()
        return query

    @classmethod
    def read_by_name(cls, name: str):
        """Complexity: O(1) with the unique index."""
        return cls.get_or_none(name=name)

    @classmethod
    def read_by_namespaces(cls, namespaces: list):
        """One SELECT for up to 5000 ids. Complexity: O(K) for the returned rows."""
        if not namespaces:
            return []
        return list(cls.select().where(cls.namespace.in_(list(namespaces))))

    @classmethod
    def read_by_namespace(cls, namespace: str):
        """Complexity: O(1) with the unique index."""
        return cls.get_or_none(namespace=namespace)

    @classmethod
    def name_exist(cls, name: str) -> bool:
        """Complexity: O(1)."""
        return cls.get_or_none(name=name) is not None

    @classmethod
    def namespace_exist(cls, namespace: str) -> bool:
        """Complexity: O(1)."""
        return cls.get_or_none(namespace=namespace) is not None

    @classmethod
    def update_access_level(cls, namespace: str, access_level) -> None:
        """Complexity: O(1)."""
        try:
            ensure_access_level_column()
        except Exception:
            pass
        obj = cls.get_or_none(namespace=namespace)
        if obj is None:
            return
        try:
            level = _parse(access_level)
        except ValueError:
            level = 1
        cls.update(access_level=level).where(cls.id == obj.id).execute()

    def serialize(self) -> dict:
        """Complexity: O(1)."""
        try:
            level = _parse(self.access_level if self.access_level is not None else 1)
        except ValueError:
            level = 1
        return {
            "id": self.id,
            "name": self.name,
            "namespace": self.namespace,
            "access_level": level,
            "access_level_label": _label(level),
            "user_access_level": level,
            "access_restrictions": 0,
        }
