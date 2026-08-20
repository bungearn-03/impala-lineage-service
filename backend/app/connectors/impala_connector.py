"""Impala connector.

Talks directly to an `impalad` HiveServer2-compatible endpoint using `impyla`
(`impala.dbapi.connect`). This is the "native" path for Impala clusters: no
Hive Metastore Thrift stubs are involved, everything goes through SQL
(`SHOW DATABASES`, `SHOW TABLES`, `DESCRIBE`, `SHOW CREATE TABLE`, ...) issued
over the same DBAPI connection that `impyla` exposes for both Impala and
HiveServer2.

The connection to the daemon is opened lazily on first use and reused for the
lifetime of the connector instance. Call `close()` (or use the connector as a
context manager, per `BaseConnector.__enter__`/`__exit__`) to release it.
"""

from __future__ import annotations

import re

from impala.dbapi import connect

from app.connectors.base import BaseConnector, ColumnMetadata, ConnectorError
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Splits a `CREATE VIEW ... AS SELECT ...` DDL string on the first top-level
# `AS` keyword. This is a heuristic regex, not a SQL parser -- see the comment
# in `get_view_definition` for the accepted limitations.
_VIEW_AS_RE = re.compile(r"\bAS\b", re.IGNORECASE | re.DOTALL)

# Matches the start of a view's `SHOW CREATE TABLE` output (Impala returns
# "CREATE VIEW ..." for views too, there's no separate "SHOW CREATE VIEW").
# Used by the `SHOW VIEWS`-unsupported fallback in `list_objects` to tell
# views apart from tables one DDL at a time.
_CREATE_VIEW_RE = re.compile(r"^\s*CREATE\s+VIEW\b", re.IGNORECASE)


class ImpalaConnector(BaseConnector):
    """Connector backed by a live Impala daemon (impalad) over `impyla`."""

    def __init__(
        self,
        host: str,
        port: int,
        database: str | None = None,
        auth_mechanism: str = "NOSASL",
        user: str | None = None,
        password: str | None = None,
        use_ssl: bool = False,
        **kwargs,
    ):
        super().__init__(
            host,
            port,
            database=database,
            auth_mechanism=auth_mechanism,
            user=user,
            password=password,
            use_ssl=use_ssl,
            **kwargs,
        )
        self.database = database
        self.auth_mechanism = auth_mechanism
        self.user = user
        self.password = password
        self.use_ssl = use_ssl
        # kwargs beyond the ones we know about are accepted and ignored
        # (e.g. extra_params from a Connection row that don't apply here).
        self._conn = None
        self._settings = get_settings()

    # -- connection management -------------------------------------------------

    def _get_connection(self):
        """Lazily open (and cache) the underlying impyla DBAPI connection."""
        if self._conn is not None:
            return self._conn
        try:
            self._conn = connect(
                host=self.host,
                port=self.port,
                database=self.database,
                auth_mechanism=self.auth_mechanism,
                user=self.user,
                password=self.password,
                use_ssl=self.use_ssl,
                timeout=self._settings.default_query_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - impyla raises a variety of error types
            raise ConnectorError(
                f"Failed to connect to Impala at {self.host}:{self.port}: {exc}"
            ) from exc
        return self._conn

    def _execute(self, sql: str) -> list[tuple]:
        """Run a query on a fresh cursor and return all fetched rows."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            try:
                cursor.execute(sql)
                return cursor.fetchall()
            finally:
                cursor.close()
        except ConnectorError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ConnectorError(f"Impala query failed ({sql!r}): {exc}") from exc

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                logger.warning("Error while closing Impala connection to %s:%s", self.host, self.port)
            finally:
                self._conn = None

    # -- identifier quoting -----------------------------------------------------

    @staticmethod
    def _quote_ident(name: str) -> str:
        return f"`{name}`"

    @classmethod
    def _qualify(cls, database: str, object_name: str) -> str:
        return f"{cls._quote_ident(database)}.{cls._quote_ident(object_name)}"

    # -- BaseConnector API --------------------------------------------------

    def test_connection(self) -> tuple[bool, str]:
        try:
            self._execute("SELECT 1")
            return True, f"Successfully connected to Impala at {self.host}:{self.port}"
        except Exception as exc:  # noqa: BLE001 - must never raise
            return False, str(exc)

    def list_databases(self) -> list[str]:
        rows = self._execute("SHOW DATABASES")
        # SHOW DATABASES returns (name, comment) on most Impala versions;
        # only the first column is the database name.
        names = {row[0] for row in rows if row}
        return sorted(names)

    def list_objects(self, database: str) -> list[tuple[str, str]]:
        table_rows = self._execute(f"SHOW TABLES IN {self._quote_ident(database)}")
        all_names = {row[0] for row in table_rows if row}

        view_names: set[str] = set()
        try:
            view_rows = self._execute(f"SHOW VIEWS IN {self._quote_ident(database)}")
            view_names = {row[0] for row in view_rows if row}
        except ConnectorError as exc:
            # Older Impala versions don't support SHOW VIEWS at all (it's a
            # relatively recent addition) -- fall back to asking each object
            # individually via its DDL instead of defaulting everything to
            # TABLE, since that would silently skip view-definition parsing
            # (and therefore all lineage) for every real view in `database`.
            logger.warning(
                "SHOW VIEWS IN %s not supported, falling back to per-object "
                "DDL inspection to detect views: %s",
                database,
                exc,
            )
            view_names = self._detect_views_via_ddl(database, all_names)

        objects: list[tuple[str, str]] = []
        for name in sorted(all_names | view_names):
            object_type = "VIEW" if name in view_names else "TABLE"
            objects.append((name, object_type))
        return objects

    def _detect_views_via_ddl(self, database: str, names: set[str]) -> set[str]:
        """Classify objects as VIEW vs TABLE by inspecting each one's DDL.

        Only used as a fallback when `SHOW VIEWS` isn't supported by the
        Impala version in use -- there's no bulk way to ask "which of these
        are views" on those versions, so this costs one `SHOW CREATE TABLE`
        query per object. A single object whose DDL fails to fetch (e.g. a
        transient error, or a kind concurrently dropped mid-scan) is treated
        as a TABLE rather than aborting the whole database's scan over it.
        """
        view_names: set[str] = set()
        for name in names:
            try:
                ddl = self.get_ddl(database, name)
            except ConnectorError as exc:
                logger.warning("Could not fetch DDL for %s.%s to detect its object type: %s", database, name, exc)
                continue
            if ddl and _CREATE_VIEW_RE.match(ddl):
                view_names.add(name)
        return view_names

    def get_columns(self, database: str, object_name: str) -> list[ColumnMetadata]:
        rows = self._execute(f"DESCRIBE {self._qualify(database, object_name)}")
        columns: list[ColumnMetadata] = []
        for idx, row in enumerate(rows):
            name = row[0]
            data_type = row[1] if len(row) > 1 else None
            columns.append(
                ColumnMetadata(
                    name=name,
                    data_type=data_type,
                    ordinal_position=idx,
                    is_nullable=True,  # Impala's DESCRIBE doesn't expose nullability
                )
            )
        return columns

    def get_ddl(self, database: str, object_name: str) -> str | None:
        rows = self._execute(f"SHOW CREATE TABLE {self._qualify(database, object_name)}")
        if not rows or not rows[0]:
            return None
        return rows[0][0]

    def get_view_definition(self, database: str, view_name: str) -> str | None:
        ddl = self.get_ddl(database, view_name)
        if not ddl:
            return None

        # Heuristic: Impala's `SHOW CREATE TABLE` for a view returns text like
        # "CREATE VIEW db.name (...) AS SELECT ...". We split on the first
        # top-level `AS` keyword (case-insensitive, DOTALL so it matches
        # across newlines) and treat everything after it as the view's SELECT
        # body. This is a text heuristic, not a SQL parser, so it can misfire
        # on pathological DDL (e.g. an "AS" appearing inside a column alias
        # or comment before the real one); if no match is found at all we
        # fall back to returning the raw DDL.
        match = _VIEW_AS_RE.search(ddl)
        if not match:
            return ddl
        return ddl[match.end():].strip()
