"""Runnable smoke test + usage examples for oracle_conn_kit.

Run:        python -m oracle_conn_kit.example
Exit code:  0 = connection OK,  1 = failed (prints reason).

It resolves credentials in this order:
1. --config path/to/config.json   (section "db" is used; also accepts a
   full main-tool config file)
2. environment variables ORACLE_HOST / ORACLE_PORT / ORACLE_SERVICE /
   ORACLE_USER / ORACLE_PASSWORD / ORACLE_SCHEMA
3. edit CONFIG below for a quick manual test
"""
import argparse
import json
import sys

from .oracle_conn import OracleClient, DatabaseConnectionError, \
    DatabaseQueryError

# fallback for a quick manual run (keep empty in git!)
CONFIG = {
    # "host": "10.x.x.x", "port": 1521, "service_name": "cc",
    # "user": "bss_ms_ai", "password": "enc:v1:...", "schema": "CC",
}


def build_client(cfg_path=None) -> OracleClient:
    if cfg_path:
        with open(cfg_path, encoding="utf-8") as f:
            data = json.load(f)
        section = data.get("db", data)  # main-tool file or bare section
        return OracleClient.from_config(section)
    if CONFIG.get("host"):
        return OracleClient.from_config(CONFIG)
    return OracleClient.from_env()


def main() -> int:
    ap = argparse.ArgumentParser(description="oracle_conn_kit smoke test")
    ap.add_argument("--config", help="path to config json (uses 'db' key)")
    args = ap.parse_args()

    try:
        db = build_client(args.config)
    except Exception as e:
        print(f"[FAIL] cannot build client: {e}")
        return 1

    try:
        with db:
            ver = db.query_one(
                "SELECT banner FROM v$version WHERE ROWNUM = 1")
            print("[OK] connected:", ver[0] if ver else "?")
            one = db.query_one("SELECT 1 FROM DUAL")
            print("[OK] SELECT 1 FROM DUAL ->", one[0])
            who = db.query_one("SELECT USER FROM DUAL")
            print("[OK] logged in as:", who[0])
            cur = db.cursor()
            try:
                cur.execute("SELECT SYS_CONTEXT('USERENV','CURRENT_SCHEMA') "
                            "FROM DUAL")
                print("[OK] CURRENT_SCHEMA:", cur.fetchone()[0])
            finally:
                cur.close()
        print("[OK] closed cleanly")
        return 0
    except DatabaseConnectionError as e:
        print(f"[FAIL] connection: {e}")
    except DatabaseQueryError as e:
        print(f"[FAIL] query: {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
