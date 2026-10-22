"""Application configuration loading (config_ocs.json), PyInstaller-aware."""
import json
import os
import sys

from core.crypto import decrypt_value
from core.errors import AppConfigError

DEFAULT_CONFIG = {
    # NOTE: shipped without real endpoints/credentials on purpose.
    # Copy config_ocs.json.example -> config_ocs.json and fill in real values.
    "db": {
        "host": "YOUR_UAT_DB_HOST",
        "port": 1521,
        "service_name": "YOUR_SERVICE_NAME",
        "user": "YOUR_DB_USER",
        "password": "CHANGE_ME"
    },
    "ssh": {
        "host": "YOUR_UAT_SSH_HOST",
        "username": "YOUR_SSH_USER",
        "password": "CHANGE_ME"
    },
    "api": {
        "base_url": "http://YOUR_API_HOST:7000"
    },
    "crm_db": {
        "host": "YOUR_UAT_DB_HOST",
        "port": 1521,
        "service_name": "YOUR_SERVICE_NAME",
        "user": "YOUR_CRM_DB_USER",
        "password": "CHANGE_ME"
    },
    "redis": {
        "nodes": [
            ["YOUR_REDIS_HOST_1", 28001], ["YOUR_REDIS_HOST_2", 28002]
        ],
        "password": None
    }
}


def get_resource_path(relative_path: str) -> str:
    """Resolve a resource path both in dev mode and when frozen by PyInstaller.

    When frozen: prefer a file placed NEXT TO THE EXE (so the config can be
    updated without rebuilding), falling back to the bundled copy.
    """
    if hasattr(sys, '_MEIPASS'):
        beside_exe = os.path.join(os.path.dirname(sys.executable), relative_path)
        if os.path.exists(beside_exe):
            return beside_exe
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        os.pardir, relative_path)


class AppConfig:
    """Typed wrapper around config_ocs.json."""

    def __init__(self, config_path: str = None):
        self.config_path = config_path or get_resource_path('config_ocs.json')
        self.db = {}
        self.ssh = {}
        self.api = {}
        self.crm_db = {}
        self.redis = {}
        self.load()

    def load(self):
        if not os.path.exists(self.config_path):
            self._write_default()
            raise AppConfigError(
                f"Config file not found. A default one has been created at:\n"
                f"{self.config_path}\nPlease edit it with correct credentials "
                f"and restart the application."
            )
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise AppConfigError(f"Failed to read config file: {e}")

        # NOTE: an optional 'schema' key may be present in db / crm_db; it is
        # NOT required - connections default CURRENT_SCHEMA to CC at connect
        # time (see db_client) so bare table names resolve for non-owner login
        # users such as the bss_ms_ai service account.
        self.db = self._section(raw, 'db', ['host', 'port', 'service_name', 'user', 'password'])
        self.ssh = self._section(raw, 'ssh', ['host', 'username', 'password'])
        self.api = self._section(raw, 'api', ['base_url'])

        # Backward compatibility: older configs lack the 'crm_db' / 'redis' sections
        if 'crm_db' in raw:
            self.crm_db = self._section(
                raw, 'crm_db', ['host', 'port', 'service_name', 'user', 'password'])
        else:
            self.crm_db = dict(DEFAULT_CONFIG['crm_db'])

        # Design note: this tool intentionally uses ONE Oracle account
        # (db.user) for everything, including the link_rb dblink queries -
        # see grant_bss_ms_ai.sql for the required DBA setup and auditing.

        # redis section is validated loosely (nodes is a list, password optional)
        if 'redis' in raw and isinstance(raw['redis'].get('nodes'), list):
            self.redis = dict(raw['redis'])
        else:
            self.redis = dict(DEFAULT_CONFIG['redis'])
        # decrypt the password the same way as the other sections
        if 'password' in self.redis:
            try:
                self.redis['password'] = decrypt_value(self.redis['password'])
            except ValueError as e:
                raise AppConfigError(f"redis.password: {e}") from e

    # Keys whose values may appear as 'enc:v1:...' ciphertext and are
    # transparently decrypted at load time.
    SENSITIVE_KEYS = ("password",)

    def _section(self, raw: dict, name: str, required_keys):
        section = raw.get(name, {})
        missing = [k for k in required_keys if k not in section]
        if missing:
            raise AppConfigError(
                f"Config section '{name}' is missing keys: {', '.join(missing)}"
            )
        section = dict(section)
        for k in self.SENSITIVE_KEYS:
            if k in section:
                try:
                    section[k] = decrypt_value(section[k])
                except ValueError as e:
                    raise AppConfigError(f"{name}.{k}: {e}") from e
        return section

    def _write_default(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        except OSError:
            pass

    @property
    def db_dsn(self) -> str:
        return f"{self.db['host']}:{self.db['port']}/{self.db['service_name']}"

    @property
    def api_base_url(self) -> str:
        return self.api['base_url'].rstrip('/')
