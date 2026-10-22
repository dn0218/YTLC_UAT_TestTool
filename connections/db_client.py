"""Oracle database connection wrapper with auto-reconnect."""
import oracledb

from core.config import AppConfig
from core.errors import DatabaseConnectionError, DatabaseQueryError
from connections.base import BaseConnection


class OracleClient(BaseConnection):
    """Thin wrapper around python-oracledb providing a ping-checked connection."""

    def __init__(self, config: AppConfig):
        super().__init__()
        self._config = config

    def get_connection(self):
        """Return a live connection, re-establishing it if the old one died."""
        if self._conn is not None:
            try:
                self._conn.ping()
                return self._conn
            except Exception:
                self.close()

        try:
            self._conn = oracledb.connect(
                user=self._config.db['user'],
                password=self._config.db['password'],
                dsn=self._config.db_dsn
            )
            # The app's SQL uses UNQUALIFIED table names (subs, acct, ...) that
            # belong to the CC schema. When the configured login user is NOT the
            # schema owner (e.g. the bss_ms_ai service account), bare names fail
            # with ORA-00942. Point the session at the owning schema so name
            # resolution works for any granted user. Harmless when user == cc.
            schema = (self._config.db.get('schema') or 'CC').upper()
            cur = self._conn.cursor()
            try:
                cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA={schema}")
            finally:
                cur.close()
            return self._conn
        except DatabaseConnectionError:
            raise
        except Exception as e:
            raise DatabaseConnectionError(f"Database connection failed: {e}") from e

    def query_one(self, sql: str, params=None):
        """Execute a SELECT and return the first row (or None)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params or [])
            return cursor.fetchone()
        except Exception as e:
            raise DatabaseQueryError(str(e)) from e
        finally:
            cursor.close()

    def query_all(self, sql: str, params=None):
        """Execute a SELECT and return all rows."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params or [])
            return cursor.fetchall()
        except Exception as e:
            raise DatabaseQueryError(str(e)) from e
        finally:
            cursor.close()

    def execute(self, sql: str, params=None) -> int:
        """Execute a DML statement and commit. Returns affected row count."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params or [])
            rowcount = cursor.rowcount
            conn.commit()
            return rowcount
        except Exception as e:
            conn.rollback()
            raise DatabaseQueryError(str(e)) from e
        finally:
            cursor.close()

    def cursor(self):
        """Escape hatch: raw cursor for advanced flows (callers must close it)."""
        return self.get_connection().cursor()

    def commit(self):
        if self._conn is not None:
            self._conn.commit()

    def rollback(self):
        if self._conn is not None:
            self._conn.rollback()


class CrmOracleClient(OracleClient):
    """Oracle client bound to the 'crm_db' config section (crm user)."""

    def __init__(self, config: AppConfig):
        super().__init__(config)
        self._section = config.crm_db

    def get_connection(self):
        if self._conn is not None:
            try:
                self._conn.ping()
                return self._conn
            except Exception:
                self.close()
        try:
            dsn = (f"{self._section['host']}:{self._section['port']}/"
                   f"{self._section['service_name']}")
            self._conn = oracledb.connect(
                user=self._section['user'],
                password=self._section['password'],
                dsn=dsn
            )
            # Same CURRENT_SCHEMA fix as the main OracleClient: bare table
            # names must resolve against the owning schema (CC), not the
            # login user's own schema.
            schema = (self._section.get('schema') or 'CC').upper()
            cur = self._conn.cursor()
            try:
                cur.execute(f"ALTER SESSION SET CURRENT_SCHEMA={schema}")
            finally:
                cur.close()
            return self._conn
        except DatabaseConnectionError:
            raise
        except Exception as e:
            raise DatabaseConnectionError(f"CRM connection failed: {e}") from e


# NOTE on database links (link_rb): queries like
#   EVENT_RECURRING_<n>@link2rb / bill_data_<n>@link2rb
# resolve the dblink against the LOGIN USER's private links. With the
# single-account (audit) design everything runs as BSS_MS_AI, so the DBA
# must create a PRIVATE dblink named link_rb FOR BSS_MS_AI (see
# grant_bss_ms_ai.sql). No secondary connection is used anywhere.
