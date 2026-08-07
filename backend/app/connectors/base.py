import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# Authoritative view-type check used as a fallback in get_object_metadata()
# below: some Impala/Hive versions raise a ParseException on `SHOW VIEWS`
# entirely (pre-dates that statement), which forces list_objects() to guess
# every name as "TABLE". The DDL text is fetched for every object regardless,
# so it doubles as ground truth for the real type.
_CREATE_VIEW_RE = re.compile(r"^\s*CREATE\s+VIEW\b", re.IGNORECASE)


@dataclass
class ColumnMetadata:
    name: str
    data_type: str
    ordinal_position: int
    is_nullable: bool = True


@dataclass
class ObjectMetadata:
    database_name: str
    object_name: str
    object_type: str  # "TABLE" | "VIEW"
    columns: list[ColumnMetadata] = field(default_factory=list)
    ddl: str | None = None
    view_definition: str | None = None


class BaseConnector(ABC):
    """Common interface implemented by ImpalaConnector and HiveMetastoreConnector.

    Any connector backing a `Connection` row must implement all of these so that
    app.metadata.* loaders and app.workers.scan_worker can treat both interchangeably.
    """

    def __init__(self, host: str, port: int, **kwargs):
        self.host = host
        self.port = port
        self.kwargs = kwargs

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """Returns (success, message)."""

    @abstractmethod
    def list_databases(self) -> list[str]:
        ...

    @abstractmethod
    def list_objects(self, database: str) -> list[tuple[str, str]]:
        """Returns list of (object_name, object_type) tuples for a database."""

    @abstractmethod
    def get_columns(self, database: str, object_name: str) -> list[ColumnMetadata]:
        ...

    @abstractmethod
    def get_ddl(self, database: str, object_name: str) -> str | None:
        """Returns the CREATE statement for a table/view, if retrievable."""

    @abstractmethod
    def get_view_definition(self, database: str, view_name: str) -> str | None:
        """Returns the underlying SELECT statement backing a view, if it is a view."""

    def get_object_metadata(self, database: str, object_name: str, object_type: str) -> ObjectMetadata:
        """Convenience combining columns + ddl + view_definition. Connectors may override for efficiency.

        ``object_type`` from ``list_objects`` is only a hint, not trusted
        blindly: on Impala/Hive versions where ``SHOW VIEWS`` isn't supported,
        list_objects() has no choice but to guess every object as "TABLE".
        The DDL fetched here is authoritative -- if it starts with
        ``CREATE VIEW``, this is a view regardless of that guess, and
        view_definition is derived accordingly rather than staying None.
        """
        ddl = self.get_ddl(database, object_name)
        resolved_type = "VIEW" if ddl and _CREATE_VIEW_RE.match(ddl) else object_type
        return ObjectMetadata(
            database_name=database,
            object_name=object_name,
            object_type=resolved_type,
            columns=self.get_columns(database, object_name),
            ddl=ddl,
            view_definition=self.get_view_definition(database, object_name) if resolved_type == "VIEW" else None,
        )

    def close(self) -> None:
        pass

    def __enter__(self) -> "BaseConnector":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class ConnectorError(Exception):
    pass
