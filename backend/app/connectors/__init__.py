from app.connectors.base import BaseConnector, ColumnMetadata, ConnectorError, ObjectMetadata
from app.core.security import decrypt_secret
from app.models.connection import Connection, ConnectionType


def get_connector(connection: Connection) -> BaseConnector:
    """Factory turning a persisted Connection row into a live connector instance."""
    password = decrypt_secret(connection.encrypted_password) if connection.encrypted_password else None

    common_kwargs = dict(
        database=connection.default_database,
        auth_mechanism=connection.auth_mechanism.value,
        user=connection.username,
        password=password,
        use_ssl=connection.use_ssl,
        **(connection.extra_params or {}),
    )

    if connection.conn_type == ConnectionType.IMPALA:
        from app.connectors.impala_connector import ImpalaConnector

        return ImpalaConnector(host=connection.host, port=connection.port, **common_kwargs)

    if connection.conn_type == ConnectionType.HIVE_METASTORE:
        from app.connectors.hive_metastore_connector import HiveMetastoreConnector

        return HiveMetastoreConnector(host=connection.host, port=connection.port, **common_kwargs)

    raise ConnectorError(f"Unsupported connection type: {connection.conn_type}")


__all__ = ["BaseConnector", "ColumnMetadata", "ObjectMetadata", "ConnectorError", "get_connector"]
