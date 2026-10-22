"""Tab 5 - SIM card attribute query & edit (crm user)."""
from connections.db_client import CrmOracleClient

# Only rows with this attr_code are shown (others hidden), kept identical
# to the standalone sim_tool_gui.py behaviour.
ATTR_FILTER_CODE = "EXP_SIM_PRODUCT_TYPE"


class SimCardService:
    """Query sim_card and edit crm.SIM_CARD_ATTR_VALUE rows."""

    def __init__(self, db: CrmOracleClient):
        self._db = db

    def query_card(self, iccid: str):
        """Return (sim_id, card_dict) or (None, None) when not found."""
        cur = self._db.get_connection().cursor()
        try:
            cur.execute("SELECT * FROM sim_card WHERE iccid = :1", [iccid])
            cols = [c[0].lower() for c in cur.description]
            rows = cur.fetchall()
            if not rows:
                return None, None
            sim_id = rows[0][0]
            card = {k: ("" if v is None else str(v))
                    for k, v in zip(cols, rows[0])}
            return sim_id, card
        finally:
            cur.close()

    def query_attrs(self, sim_id):
        """Return the filtered attribute rows for a SIM card."""
        sql = """SELECT p.ROWID, p.attr_value, a.attr_name, a.attr_code
                   FROM sim_card_attr_value p, attr a
                  WHERE p.sim_card_id = :1
                    AND p.attr_id = a.attr_id
                    AND a.attr_code = :2
                  ORDER BY a.attr_code"""
        cur = self._db.get_connection().cursor()
        try:
            cur.execute(sql, [sim_id, ATTR_FILTER_CODE])
            return [{"rowid": str(r[0]),
                     "value": "" if r[1] is None else str(r[1]),
                     "name":  "" if r[2] is None else str(r[2]),
                     "code":  "" if r[3] is None else str(r[3])}
                    for r in cur.fetchall()]
        finally:
            cur.close()

    def update_attr_value(self, rowid: str, new_value: str) -> str:
        """UPDATE by ROWID; verify exactly one row changed, else rollback.

        Returns the verified new value read back from the DB.
        Raises RuntimeError when rowcount != 1 (rolled back).
        """
        conn = self._db.get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE crm.SIM_CARD_ATTR_VALUE SET attr_value = :1 "
                "WHERE ROWID = :2", [new_value, rowid])
            if cur.rowcount != 1:
                conn.rollback()
                raise RuntimeError(
                    f"Updated {cur.rowcount} rows (expected 1), rolled back")
            conn.commit()
            cur.execute(
                "SELECT attr_value FROM crm.SIM_CARD_ATTR_VALUE WHERE ROWID = :1",
                [rowid])
            return cur.fetchone()[0]
        finally:
            cur.close()
