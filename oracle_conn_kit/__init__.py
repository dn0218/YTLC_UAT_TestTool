"""oracle_conn_kit - standalone Oracle DB connection kit.

Reuse the exact connection method of YTLC_UAT_TestTool in any other
program / agent, with zero imports from the parent project.

Quick start:

    from oracle_conn_kit import OracleClient

    db = OracleClient.from_config({
        "host": "10.x.x.x", "port": 1521,
        "service_name": "cc", "user": "bss_ms_ai",
        "password": "enc:v1:....",        # plain text also accepted
        "schema": "CC",
    })
    row = db.query_one("SELECT 1 FROM DUAL")
    db.close()

Only dependency: `pip install oracledb`  (thin mode - no Oracle Client needed).
"""
from .oracle_conn import OracleClient, BaseConnection

__all__ = ["OracleClient", "BaseConnection"]
__version__ = "1.0.0"
