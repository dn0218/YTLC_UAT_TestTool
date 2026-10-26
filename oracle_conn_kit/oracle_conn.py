"""Self-contained Oracle connection module (thin mode, auto-reconnect).

Connection method (identical to the main project):
- python-oracledb THIN mode -> no Oracle Client installation required.
- DSN format:  host:port/service_name  (no tnsnames.ora involved).
- Lazy connect + PING check on every acquire: dead connections are
  transparently re-established, so long-running agents survive DB
  session timeouts / firewall idle disconnects.
- After connect, ALTER SESSION SET CURRENT_SCHEMA=<schema> so that
  UNQUALIFIED table names (subs, prod, e_invoice, ...) resolve against
  the owning schema even when the login user is a granted service
  account (e.g. BSS_MS_AI) - otherwise ORA-00942.
- DML methods auto-commit on success, auto-rollback on error.
"""
import os

import oracledb

try:  # optional: reuse the project's enc:v1: implementation when available
    from core.crypto import decrypt_value, encrypt_value  # type: ignore
except ImportError:  # standalone fallback, same algorithm as core/crypto.py
    import base64
    import hashlib
    import hmac

    _PREFIX = "enc:v1:"
    _K1 = bytes.fromhex("5f2a7c91e4b08d36a1f4c5e29b7d3a88")
    _K2 = bytes.fromhex("6d1e9f4a2c8b7e5d0a3f6c9b1e8d4a72")
    _KEY = hashlib.sha256(_K1 + bytes([0x50]) + _K2).digest()

    def _keystream(nonce: bytes, length: int) -> bytes:
        out, counter = b"", 0
        while len(out) < length:
            out += hmac.new(_KEY, nonce + counter.to_bytes(4, "big"),
                            hashlib.sha256).digest()
            counter += 1
        return out[:length]

    def decrypt_value(value):
        if not isinstance(value, str) or not value.startswith(_PREFIX):
            return value
        raw = base64.b64decode(value[len(_PREFIX):])
        nonce, ct, tag = raw[:8], raw[8:-8], raw[-8:]
        expected = hmac.new(_KEY, nonce + ct, hashlib.sha256).digest()[:8]
        if not hmac.compare_digest(tag, expected):
            raise ValueError("integrity check failed (wrong key or tampered)")
        return bytes(a ^ b for a, b in
                     zip(ct, _keystream(nonce, len(ct)))).decode("utf-8")

    def encrypt_value(plaintext: str, nonce: bytes = None) -> str:
        if nonce is None:
            nonce = hashlib.sha256(plaintext.encode("utf-8")).digest()[:8]
        data = plaintext.encode("utf-8")
        ct = bytes(a ^ b for a, b in zip(data, _keystream(nonce, len(data))))
        tag = hmac.new(_KEY, nonce + ct, hashlib.sha256).digest()[:8]
        return _PREFIX + base64.b64encode(nonce + ct + tag).decode("ascii")


class AppConfigError(Exception):
    """Config section missing or invalid."""


class DatabaseConnectionError(Exception):
    """Oracle connection could not be established."""


class DatabaseQueryError(Exception):
    """SQL execution failed."""


class BaseConnection:
    """Lazy, reusable connection holder."""

    def __init__(self):
        self._conn = None

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


class OracleClient(BaseConnection):
    """Thin-mode Oracle client with ping-checked auto-reconnect.

    Construct directly, or via from_config() / from_env() helpers.
    """

    def __init__(self, user, password, dsn=None, host=None, port=1521,
                 service_name=None, schema="CC"):
        super().__init__()
        if not dsn:
            if not (host and service_name):
                raise AppConfigError(
                    "provide either dsn= or host=+service_name=")
            dsn = f"{host}:{port}/{service_name}"
        self._user = user
        self._password = decrypt_value(password) if isinstance(password, str) \
            else password
        self._dsn = dsn
        self._schema = (schema or "CC").upper()

    # ------------------------------------------------------------ builders
    @classmethod
    def from_config(cls, section: dict) -> "OracleClient":
        """Build from a JSON config section (same shape as the main tool):

            {"host": "...", "port": 1521, "service_name": "...",
             "user": "...", "password": "...",          # enc:v1: ok
             "schema": "CC"}                            # optional
        """
        try:
            return cls(
                user=section["user"],
                password=section["password"],
                host=section["host"],
                port=int(section.get("port", 1521)),
                service_name=section["service_name"],
                schema=section.get("schema") or "CC",
            )
        except KeyError as e:
            raise AppConfigError(f"config section missing key: {e}") from e

    @classmethod
    def from_env(cls, prefix="ORACLE_") -> "OracleClient":
        """Build from environment variables (handy for agents/schedulers):

            ORACLE_HOST / ORACLE_PORT / ORACLE_SERVICE
            ORACLE_USER / ORACLE_PASSWORD (enc:v1: ok) / ORACLE_SCHEMA
        """
        vals = {k[len(prefix):].lower(): v
                for k, v in os.environ.items()
                if k.startswith(prefix)}
        return cls(
            user=vals.get("user"),
            password=vals.get("password"),
            host=vals.get("host"),
            port=int(vals.get("port", 1521)),
            service_name=vals.get("service"),
            schema=vals.get("schema") or "CC",
        )

    # ------------------------------------------------------------ core
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
                user=self._user, password=self._password, dsn=self._dsn)
            # Unqualified table names must resolve against the owning
            # schema, not the login user's own schema (ORA-00942 fix).
            cur = self._conn.cursor()
            try:
                cur.execute(
                    f"ALTER SESSION SET CURRENT_SCHEMA={self._schema}")
            finally:
                cur.close()
            return self._conn
        except Exception as e:
            self.close()
            raise DatabaseConnectionError(
                f"Database connection failed ({self._dsn}): {e}") from e

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
        """Execute DML; commit on success, rollback on error.

        Returns affected row count.
        """
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
        """Escape hatch: raw cursor for advanced flows (caller closes it)."""
        return self.get_connection().cursor()

    def commit(self):
        if self._conn is not None:
            self._conn.commit()

    def rollback(self):
        if self._conn is not None:
            self._conn.rollback()

    # context-manager support: with OracleClient(...) as db: ...
    def __enter__(self):
        self.get_connection()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
        return False
