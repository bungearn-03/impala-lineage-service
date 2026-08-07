"""One-off script to register an Impala Connection row from environment variables.

Reads IMPALA_* variables at run time -- never hardcode credentials here.
Safe to re-run: if a Connection with the given name already exists, its
fields are updated in place instead of creating a duplicate.

Usage (from the backend/ directory, with the venv/deps active and
DATABASE_URL already pointing at a migrated Postgres):

    # PowerShell
    $env:IMPALA_HOST="10.10.10.200"
    $env:IMPALA_PORT="21051"
    $env:IMPALA_USER="natchaporn_so"
    $env:IMPALA_PASS="********"
    python scripts/seed_connections.py

    # Unix shell
    IMPALA_HOST=10.10.10.200 IMPALA_PORT=21051 IMPALA_USER=natchaporn_so \
        IMPALA_PASS='********' python scripts/seed_connections.py

Or simply put the IMPALA_* variables in backend/.env alongside the rest of
the app's settings and run `python scripts/seed_connections.py` with no
inline env vars -- python-dotenv (loaded by pydantic-settings for Settings)
does not automatically apply to this script's own os.environ reads, so this
script loads backend/.env itself via python-dotenv before reading IMPALA_*.

Env vars read by this script:
    IMPALA_HOST              (required)
    IMPALA_PORT              (required, integer)
    IMPALA_USER              (required)
    IMPALA_PASS              (optional, default "")
    IMPALA_DEFAULT_DATABASE  (optional, default "default")
    IMPALA_CONNECTION_NAME   (optional, default "impala-primary")
    IMPALA_AUTH_MECHANISM    (optional, default "LDAP" -- NOSASL|PLAIN|LDAP|KERBEROS;
                              LDAP is the common choice for Impala username/password auth)
    IMPALA_USE_SSL           (optional, "true"/"false", default "false")
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

from app.core.database import session_scope  # noqa: E402
from app.core.security import encrypt_secret  # noqa: E402
from app.models.connection import AuthMechanism, Connection, ConnectionType  # noqa: E402


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def main() -> None:
    host = _require_env("IMPALA_HOST")
    port = int(_require_env("IMPALA_PORT"))
    username = _require_env("IMPALA_USER")
    password = os.environ.get("IMPALA_PASS", "")

    default_database = os.environ.get("IMPALA_DEFAULT_DATABASE", "default")
    connection_name = os.environ.get("IMPALA_CONNECTION_NAME", "impala-primary")
    auth_mechanism = AuthMechanism(os.environ.get("IMPALA_AUTH_MECHANISM", "LDAP"))
    use_ssl = _bool_env("IMPALA_USE_SSL", False)

    with session_scope() as db:
        connection = db.query(Connection).filter(Connection.name == connection_name).one_or_none()

        if connection is None:
            connection = Connection(name=connection_name, conn_type=ConnectionType.IMPALA)
            db.add(connection)
            action = "Created"
        else:
            action = "Updated"

        connection.conn_type = ConnectionType.IMPALA
        connection.host = host
        connection.port = port
        connection.default_database = default_database
        connection.auth_mechanism = auth_mechanism
        connection.username = username
        connection.encrypted_password = encrypt_secret(password) if password else None
        connection.use_ssl = use_ssl

        db.flush()
        print(f"{action} connection {connection_name!r} -> {host}:{port} (id={connection.id})")


if __name__ == "__main__":
    main()
