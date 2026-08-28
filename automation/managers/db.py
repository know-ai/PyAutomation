# -*- coding: utf-8 -*-
"""automation/managers/logger.py

This module implements the Database Manager (DBManager), which orchestrates database interactions,
table registration, and logging engines for various system components.
"""
import logging, queue
from peewee import MySQLDatabase, PostgresqlDatabase, SqliteDatabase
from playhouse.migrate import (
    MySQLMigrator,
    PostgresqlMigrator,
    SqliteMigrator,
    migrate,
)
from ..singleton import Singleton
from ..logger.datalogger import DataLoggerEngine
from ..logger.logdict import  LogTable
from ..logger.alarms import AlarmsLoggerEngine
from ..logger.events import EventsLoggerEngine
from ..logger.users import UsersLoggerEngine
from ..logger.logs import LogsLoggerEngine
from ..logger.machines import MachinesLoggerEngine
from ..logger.opcua_server import OPCUAServerLoggerEngine
from ..tags import CVTEngine, TagObserver
from ..modules.users.users import User
from ..utils.decorators import logging_error_handler
from ..dbmodels import (
    Manufacturer,
    Segment,
    Tags, 
    TagValue, 
    AlarmTypes,
    AlarmStates, 
    Alarms,  
    AlarmSummary, 
    Variables, 
    Units, 
    DataTypes,
    OPCUA,
    Users,
    Roles,
    Events,
    Logs,
    Machines,
    TagsMachines,
    AccessType,
    OPCUAServer,
    LinearReferencingGeospatial,
    BaseModel,
    Nodes,
    HMISession,
    UserApiSession,
    CatalogVersions,
)


class DBManager(Singleton):
    r"""
    Central manager for database operations and historical data logging.

    It manages the connection to the database (SQLite, PostgreSQL, MySQL), registers database models,
    and initializes specific logging engines for Alarms, Events, Users, etc.
    """

    def __init__(self, period:float=1.0, delay:float=1.0, drop_tables:bool=False):

        self._period = period
        self._delay = delay
        self._drop_tables = drop_tables
        self._tag_queue = queue.Queue(maxsize=1)
        self.engine = CVTEngine()
        self._logging_tags = LogTable()
        self._logger = DataLoggerEngine()
        self.alarms_logger = AlarmsLoggerEngine()
        self.events_logger = EventsLoggerEngine()
        self.users_logger = UsersLoggerEngine()
        self.logs_logger = LogsLoggerEngine()
        self.machines_logger = MachinesLoggerEngine()
        self.opcuaserver_logger = OPCUAServerLoggerEngine()
        self._tables = [
            Nodes,
            HMISession,
            UserApiSession,
            Manufacturer,
            Segment,
            Variables, 
            Units, 
            DataTypes, 
            Tags, 
            TagValue, 
            AlarmTypes,
            AlarmStates, 
            Alarms,
            AlarmSummary,
            OPCUA,
            Roles,
            Users,
            Events,
            Logs,
            Machines,
            TagsMachines,
            LinearReferencingGeospatial,
            AccessType,
            OPCUAServer,
            CatalogVersions,
        ]

        self._extra_tables = []
        
    @logging_error_handler
    def get_queue(self)->queue.Queue:
        r"""
        Retrieves the internal queue used for tag updates.
        """
        return self._tag_queue

    @logging_error_handler
    def set_db(self, db, is_history_logged:bool=False):
        r"""
        Configures the database connection for all logging engines.

        **Parameters:**

        * **db** (Database): The Peewee database instance (SqliteDatabase, PostgresqlDatabase, MySQLDatabase).
        * **is_history_logged** (bool, optional): Enables or disables historical data logging.
        """
        self._logger.set_db(db)
        self._logger.logger.set_is_history_logged(value=is_history_logged)
        self.alarms_logger.set_db(db)
        self.alarms_logger.logger.set_is_history_logged(value=is_history_logged)
        self.events_logger.set_db(db)
        self.events_logger.logger.set_is_history_logged(value=is_history_logged)
        self.users_logger.set_db(db)
        self.logs_logger.set_db(db)
        self.logs_logger.logger.set_is_history_logged(value=is_history_logged)
        self.machines_logger.set_db(db)
        self.opcuaserver_logger.logger.set_db(db)
        
    @logging_error_handler
    def get_db(self):
        r"""
        Retrieves the current database connection object.
        """
        return self._logger.get_db()

    @logging_error_handler
    def set_dropped(self, drop_tables:bool):
        r"""
        Sets the flag to drop tables on initialization.

        **Parameters:**

        * **drop_tables** (bool): If True, tables will be dropped and recreated on startup.
        """
        self._drop_tables = drop_tables

    @logging_error_handler
    def get_dropped(self)->bool:
        r"""
        Gets the drop tables flag status.
        """
        return self._drop_tables

    @logging_error_handler
    def register_table(self, cls:BaseModel):
        r"""
        Registers a new database model (table) to be managed by the system.

        **Parameters:**

        * **cls** (BaseModel): A class inheriting from `BaseModel`.
        """
        self._tables.append(cls)

    @logging_error_handler
    def get_db_table(self, tablename:str):
        r"""
        Retrieves a registered table model by its table name.

        **Parameters:**

        * **tablename** (str): The name of the table in the database.

        **Returns:**

        * **Model**: The Peewee model class if found, else None.
        """
        for table in self._tables:

            if table._meta.table_name.lower()==tablename.lower():

                return table
            
        return None

    def create_tables(self):
        r"""
        Creates all registered tables in the database.
        """
        self._tables.extend(self._extra_tables)
        self._logger.create_tables(self._tables)
        self.alarms_logger.create_tables(self._tables)
        self.ensure_schema()

    def ensure_schema(self):
        """Add nullable scope columns and indexes without inferring ownership."""
        db = self.get_db()
        if db is None:
            return
        db.create_tables(self._tables, safe=True)
        migrator_type = (
            SqliteMigrator
            if isinstance(db, SqliteDatabase)
            else (
                PostgresqlMigrator
                if isinstance(db, PostgresqlDatabase)
                else MySQLMigrator
                if isinstance(db, MySQLDatabase)
                else None
            )
        )
        if migrator_type is None:
            raise TypeError(f"Unsupported database for schema migration: {type(db).__name__}")
        migrator = migrator_type(db)
        scoped_fields = (
            (Tags, "area"),
            (Tags, "owner_node"),
            (OPCUA, "owner_node"),
            (Machines, "area"),
            (Alarms, "area"),
            (TagValue, "area"),
            (AlarmSummary, "area"),
            (Events, "area"),
            (Logs, "area"),
        )
        for model, field_name in scoped_fields:
            existing = {column.name for column in db.get_columns(model._meta.table_name)}
            if field_name not in existing:
                field = model._meta.fields[field_name].clone()
                field.index = False
                migrate(
                    migrator.add_column(
                        model._meta.table_name,
                        field_name,
                        field,
                    )
                )
        for model in {model for model, _ in scoped_fields}:
            model._schema.create_indexes(safe=True)
        self._ensure_machine_temporal_schema(db, migrator)
        self._ensure_machine_name_partition(db)
        self._ensure_nodes_clock_schema(db, migrator)
        self._ensure_tag_filter_schema(db, migrator)

    def _drop_legacy_tag_columns(self, db, migrator=None):
        if db is None:
            return
        legacy = ("gaussian_filter", "gaussian_filter_threshold", "gaussian_filter_r_value", "process_filter")
        try:
            existing = {column.name for column in db.get_columns(Tags._meta.table_name)}
        except Exception:
            return
        to_drop = [name for name in legacy if name in existing]
        if not to_drop:
            return
        vendor = getattr(db, "vendor", "") or ""
        table = Tags._meta.table_name
        logger = logging.getLogger("pyautomation")
        try:
            if vendor == "postgresql":
                cols = ", ".join(f'DROP COLUMN IF EXISTS "{name}"' for name in to_drop)
                db.execute_sql(f'ALTER TABLE "{table}" {cols};')
            elif vendor == "mysql":
                for name in to_drop:
                    db.execute_sql(f"ALTER TABLE `{table}` DROP COLUMN `{name}`;")
            else:
                drop_migrator = migrator or SqliteMigrator(db)
                for name in to_drop:
                    migrate(drop_migrator.drop_column(table, name))
            logger.info("Dropped legacy tag columns: %s", ", ".join(to_drop))
        except Exception:
            logger.warning("Legacy tag column drop skipped", exc_info=True)

    def _ensure_tag_filter_schema(self, db, migrator):
        table = Tags._meta.table_name
        try:
            existing = {column.name for column in db.get_columns(table)}
        except Exception:
            return
        additions = (
            ("filter_enabled", Tags.filter_enabled),
            ("filter_wavelet", Tags.filter_wavelet),
            ("filter_level", Tags.filter_level),
            ("filter_threshold_factor", Tags.filter_threshold_factor),
            ("filter_persist", Tags.filter_persist),
        )
        for field_name, field in additions:
            if field_name not in existing:
                cloned = field.clone()
                cloned.index = False
                migrate(
                    migrator.add_column(
                        table,
                        field_name,
                        cloned,
                    )
                )
        self._drop_legacy_tag_columns(db, migrator)

    def _ensure_nodes_clock_schema(self, db, migrator):
        table = Nodes._meta.table_name
        try:
            existing = {column.name for column in db.get_columns(table)}
        except Exception:
            return
        additions = (
            ("ntp_offset_ms", Nodes.ntp_offset_ms),
            ("ntp_synced", Nodes.ntp_synced),
            ("ntp_updated_at", Nodes.ntp_updated_at),
        )
        for field_name, field in additions:
            if field_name not in existing:
                cloned = field.clone()
                cloned.index = False
                migrate(
                    migrator.add_column(
                        table,
                        field_name,
                        cloned,
                    )
                )

    def _ensure_machine_temporal_schema(self, db, migrator):
        """Add execution_interval / sample_interval / sample_override and backfill."""

        machine_columns = {column.name for column in db.get_columns(Machines._meta.table_name)}
        temporal_fields = (
            ("execution_interval", Machines.execution_interval),
            ("sample_interval", Machines.sample_interval),
        )
        for field_name, field in temporal_fields:
            if field_name not in machine_columns:
                cloned = field.clone()
                cloned.index = False
                migrate(
                    migrator.add_column(
                        Machines._meta.table_name,
                        field_name,
                        cloned,
                    )
                )
        try:
            Machines.update(execution_interval=Machines.interval).where(
                Machines.execution_interval.is_null()
            ).execute()
        except Exception:
            logging.getLogger("pyautomation").debug(
                "execution_interval backfill skipped",
                exc_info=True,
            )
        link_table = TagsMachines._meta.table_name
        try:
            link_columns = {column.name for column in db.get_columns(link_table)}
        except Exception:
            return
        if "sample_override" not in link_columns:
            cloned = TagsMachines.sample_override.clone()
            cloned.index = False
            migrate(
                migrator.add_column(
                    link_table,
                    "sample_override",
                    cloned,
                )
            )

    def _ensure_machine_name_partition(self, db) -> None:
        """Drop global UNIQUE(machines.name); uniqueness is (area, name) when area is set."""
        from ..catalog.partition import ensure_machine_name_partition

        ensure_machine_name_partition(db)

    @logging_error_handler
    def drop_tables(self):
        r"""
        Drops all registered tables from the database.
        """
        tables = self._tables
        
        self._logger.drop_tables(tables)

    @logging_error_handler
    def clear_default_tables(self):
        r"""
        Clears the list of default tables. Useful for custom applications that don't need the standard schema.
        """
        self._tables = []

    @logging_error_handler
    def get_tags(self)->dict:
        r"""
        Retrieves all tags configured in the database logger.
        """
        return self._logger.get_tags()
    
    @logging_error_handler
    def get_alarms(self)->dict:
        r"""
        Retrieves all alarms from the alarm logger.
        """

        return self.alarms_logger.get_alarms()

    @logging_error_handler
    def set_tag(
        self, 
        tag:str, 
        unit:str, 
        data_type:str, 
        description:str,
        display_name:str="", 
        min_value:float=None, 
        max_value:float=None, 
        tcp_source_address:str=None, 
        node_namespace:str=None):
        r"""
        Registers a tag in the database logger configuration.

        **Parameters:**

        * **tag** (str): Tag name.
        * **unit** (str): Tag unit.
        * **data_type** (str): Data type (float, int, bool).
        * **description** (str): Description.
        * **tcp_source_address** (str, optional): OPC UA server address.
        * **node_namespace** (str, optional): OPC UA Node ID.
        """
        self._logger.set_tag(
            tag=tag,  
            unit=unit,
            data_type=data_type,
            description=description,
            display_name=display_name,
            min_value=min_value,
            max_value=max_value,
            tcp_source_address=tcp_source_address,
            node_namespace=node_namespace
        )

    @logging_error_handler
    def set_tags(self):
        r"""
        Applies all staged tags from the LogTable to the database logger.
        """
        for period in self._logging_tags.get_groups():
            
            tags = self._logging_tags.get_tags(period)
        
            for tag, unit, data_type, description, display_name, min_value, max_value, tcp_source_address, node_namespace in tags:

                self.set_tag(
                    tag=tag,
                    unit=unit, 
                    data_type=data_type, 
                    description=description, 
                    display_name=display_name,
                    min_value=min_value, 
                    max_value=max_value, 
                    tcp_source_address=tcp_source_address, 
                    node_namespace=node_namespace)

    @logging_error_handler
    def init_database(self):
        r"""
        Initializes the database schema. Drops tables if configured, then creates them.
        """
        if self.get_dropped():
            try:
                self.drop_tables()
            except Exception as e:
                error = str(e)
                logger = logging.getLogger("pyautomation")
                logger.error("Database:{}".format(error))
        
        self.create_tables()

    @logging_error_handler
    def stop_database(self):
        r"""
        Closes the database connection.
        """
        self._logger.stop_db()

    @logging_error_handler
    def get_opcua_clients(self):
        r"""
        Retrieves all OPC UA client configurations from the database.
        """
        return OPCUA.read_all()

    def scoped_query(
        self,
        model: type[BaseModel],
        *,
        area: str = None,
        owner_node: str = None,
    ):
        if model not in self._tables:
            raise ValueError(f"{model.__name__} is not a registered database model")
        return model.scoped(area=area, owner_node=owner_node)

    def get_tags_scoped(self, area: str, owner_node: str = None):
        return Tags.read_scoped(area=area, owner_node=owner_node)

    def get_opcua_clients_scoped(self, owner_node: str):
        return OPCUA.read_scoped(owner_node=owner_node)

    def get_machines_scoped(self, area: str):
        return Machines.read_config_scoped(area=area)

    def get_alarms_scoped(self, area: str):
        return Alarms.read_scoped(area=area)

    def register_node(
        self,
        node_id: str,
        area: str,
        *,
        site: str = None,
        hostname: str = None,
        version: str = None,
    ):
        return Nodes.register(
            node_id=node_id,
            area=area,
            site=site,
            hostname=hostname,
            version=version,
        )

    def update_node_clock_status(
        self,
        node_id: str,
        *,
        ntp_synced: bool | None,
        ntp_offset_ms: float | None,
    ):
        return Nodes.update_clock_status(
            node_id=node_id,
            ntp_synced=ntp_synced,
            ntp_offset_ms=ntp_offset_ms,
        )

    def heartbeat_node(self, node_id: str, now=None):
        return Nodes.heartbeat(node_id, now=now)

    def list_stale_peer_ids(self, node_id: str, *, older_than_s: float = 90.0, now=None):
        return Nodes.stale_peer_ids(node_id, older_than_s=older_than_s, now=now)

    # USERS METHODS
    @logging_error_handler
    def set_role(self, name:str, level:int, identifier:str):
        r"""
        Creates a new user role in the database.
        """
        result = self.users_logger.set_role(name=name, level=level, identifier=identifier)
        try:
            from ..catalog.bootstrap import write_catalog_row

            write_catalog_row(
                "roles",
                {"name": name, "level": level, "identifier": identifier},
            )
        except Exception:
            logging.debug("catalog role mirror skipped", exc_info=True)
        return result

    @logging_error_handler
    def set_user(self, user:User):
        r"""
        Creates a new user in the database.
        """
        result = self.users_logger.set_user(user=user)
        try:
            from ..catalog.bootstrap import write_catalog_row

            write_catalog_row(
                "users",
                {
                    "username": getattr(user, "username", None),
                    "email": getattr(user, "email", None),
                    "password": getattr(user, "password", None),
                    "identifier": getattr(user, "identifier", None),
                    "name": getattr(user, "name", None),
                    "lastname": getattr(user, "lastname", None),
                },
            )
        except Exception:
            logging.debug("catalog user mirror skipped", exc_info=True)
        return result
    
    @logging_error_handler
    def login(self, password:str, username:str="", email:str=""):
        r"""
        Authenticates a user against the database.
        """
        return self.users_logger.login(password=password, username=username, email=email)
    
    @logging_error_handler
    def update_password(self, username:str, new_password:str):
        r"""
        Updates a user's password in the database.
        """
        return self.users_logger.update_password(username=username, new_password=new_password)
    
    @logging_error_handler
    def update_role(self, username:str, new_role_name:str):
        r"""
        Updates a user's role in the database.
        """
        return self.users_logger.update_role(username=username, new_role_name=new_role_name)

    @logging_error_handler
    def summary(self)->dict:
        r"""
        Generates a summary of the database manager configuration.

        **Returns:**

        * **dict**: Summary including period, configured tags, and delay.
        """
        result = dict()

        result["period"] = self._period
        result["tags"] = self.get_tags()
        result["delay"] = self._delay

        return result
    
    @logging_error_handler
    def attach(self, tag_name:str):
        r"""
        Attaches an observer to a tag for database logging purposes.
        """
        tag = self.engine.get_tag_by_name(name=tag_name)
        if tag is None:
            return
        for observer in tag._observers:
            if isinstance(observer, TagObserver):
                return
        observer = TagObserver(self._tag_queue)
        self.engine.attach(name=tag_name, observer=observer)
