"""Hive Metastore connector.

Design decision: rather than speaking the raw Hive Metastore Thrift protocol
directly (`ThriftHiveMetastore`), which requires generated Python stubs that
must match the exact Hive Metastore version deployed on the cluster (and
which aren't vendored in this project -- see requirements.txt, only
`impyla`/`thrift`/`thrift-sasl`/`pure-sasl`/`sasl` are available, with no
generated Hive Metastore Thrift stubs), this connector instead talks to
**HiveServer2** using the same `impyla` DBAPI client used by
`ImpalaConnector` (`from impala.dbapi import connect`). `impyla` supports both
Impala daemons and HiveServer2 over the same wire protocol, so we get table,
column, and DDL metadata via plain HiveQL (`SHOW DATABASES`, `SHOW TABLES`,
`DESCRIBE`, `SHOW CREATE TABLE`, `DESCRIBE FORMATTED`, ...) instead of
hand-rolled Thrift calls. This is more portable across Hive versions and
needs no extra generated/vendored code.

As with `ImpalaConnector`, the underlying connection is opened lazily on
first use and cached on the instance; call `close()` (or use the connector
as a context manager) to release it.
"""

from __future__ import annotations

import re

from impala.dbapi import connect

from app.connectors.base import BaseConnector, ColumnMetadata, ConnectorError
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Fallback heuristic (mirrors ImpalaConnector): splits a
# `CREATE VIEW ... AS SELECT ...` DDL string on the first top-level `AS`
# keyword. Only used when DESCRIBE FORMATTED doesn't yield a usable
# View Original/Expanded Text.
_VIEW_AS_RE = re.compile(r"\bAS\b", re.IGNORECASE | re.DOTALL)

_VIEW_TEXT_PREFIXES = ("View Original Text:", "View Expanded Text:")


class HiveMetastoreConnector(BaseConnector):
    """Connector backed by HiveServer2, accessed over the `impyla` DBAPI.

    See the module docstring for why this doesn't speak raw Hive Metastore
    Thrift.
    """

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
        # Extra kwargs (e.g. extra_params from a Connection row that don't
        # apply to this connector) are accepted and ignored.
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
                f"Failed to connect to HiveServer2 at {self.host}:{self.port}: {exc}"
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
            raise ConnectorError(f"HiveServer2 query failed ({sql!r}): {exc}") from exc

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                logger.warning("Error while closing HiveServer2 connection to %s:%s", self.host, self.port)
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
            return True, f"Successfully connected to HiveServer2 at {self.host}:{self.port}"
        except Exception as exc:  # noqa: BLE001 - must never raise
            return False, str(exc)

    def list_databases(self) -> list[str]:
        rows = self._execute("SHOW DATABASES")
        # SHOW DATABASES returns a single database_name column in Hive.
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
            # SHOW VIEWS requires Hive >= 2.2. On older versions, fall back to
            # treating every name from SHOW TABLES as a TABLE (unknown type).
            logger.warning(
                "SHOW VIEWS IN %s not supported, falling back to TABLE for all objects: %s",
                database,
                exc,
            )

        objects: list[tuple[str, str]] = []
        for name in sorted(all_names | view_names):
            object_type = "VIEW" if name in view_names else "TABLE"
            objects.append((name, object_type))
        return objects

    def get_columns(self, database: str, object_name: str) -> list[ColumnMetadata]:
        rows = self._execute(f"DESCRIBE {self._qualify(database, object_name)}")
        columns: list[ColumnMetadata] = []
        idx = 0
        for row in rows:
            if not row:
                continue
            name = (row[0] or "").strip()
            # Hive's DESCRIBE output includes footer rows for partition
            # metadata (e.g. "", "# Partition Information", "# col_name",
            # "partition_col", ...). Skip anything blank or starting with "#".
            if not name or name.startswith("#"):
                continue
            data_type = row[1] if len(row) > 1 else None
            columns.append(
                ColumnMetadata(
                    name=name,
                    data_type=data_type,
                    ordinal_position=idx,
                    is_nullable=True,  # Hive's DESCRIBE doesn't expose nullability
                )
            )
            idx += 1
        return columns

    def get_ddl(self, database: str, object_name: str) -> str | None:
        rows = self._execute(f"SHOW CREATE TABLE {self._qualify(database, object_name)}")
        if not rows:
            return None
        # Hive's SHOW CREATE TABLE returns one createtab_stmt column, one
        # line of DDL per row; join them back into a single string.
        lines = [row[0] for row in rows if row and row[0] is not None]
        if not lines:
            return None
        return "\n".join(lines)

    def get_view_definition(self, database: str, view_name: str) -> str | None:
        # Preferred path: DESCRIBE FORMATTED exposes the view's stored SELECT
        # text directly, which is more reliable than parsing DDL text.
        try:
            rows = self._execute(f"DESCRIBE FORMATTED {self._qualify(database, view_name)}")
        except ConnectorError as exc:
            logger.warning(
                "DESCRIBE FORMATTED %s.%s failed, falling back to DDL regex extraction: %s",
                database,
                view_name,
                exc,
            )
            rows = []

        original_text: str | None = None
        expanded_text: str | None = None
        for row in rows:
            if not row:
                continue
            col_name = (row[0] or "").strip()
            for prefix in _VIEW_TEXT_PREFIXES:
                if not col_name.startswith(prefix):
                    continue
                # impyla returns DESCRIBE FORMATTED rows as
                # (col_name, data_type, comment). The view text may be split
                # across the col_name (after the prefix) and the data_type
                # ("value") column depending on Hive version/formatting.
                remainder = col_name[len(prefix):].strip()
                value_col = (row[1] or "").strip() if len(row) > 1 else ""
                text = " ".join(part for part in (remainder, value_col) if part).strip()
                if not text:
                    continue
                if prefix == "View Original Text:":
                    original_text = text
                else:
                    expanded_text = text

        view_text = original_text or expanded_text
        if view_text:
            return view_text

        # Fallback: same regex-based extraction used by ImpalaConnector,
        # splitting the DDL on the first top-level AS keyword. This is a
        # heuristic, not a SQL parser -- see ImpalaConnector.get_view_definition.
        ddl = self.get_ddl(database, view_name)
        if not ddl:
            return None
        match = _VIEW_AS_RE.search(ddl)
        if not match:
            return ddl
        return ddl[match.end():].strip()
