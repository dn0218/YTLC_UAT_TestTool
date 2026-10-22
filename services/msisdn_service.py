"""Core 3 - Remove trailing '0' from an MSISDN across OCS tables."""
from connections.db_client import OracleClient
from core.errors import BusinessRuleError
from core.models import MsisdnInfo


class MsisdnService:
    """Validate an MSISDN and rename it in subs / crm.acc_nbr / cc.acc_nbr."""

    def __init__(self, db: OracleClient):
        self._db = db

    def validate(self, msisdn: str) -> MsisdnInfo:
        if not msisdn.endswith('0'):
            raise BusinessRuleError(f"MSISDN '{msisdn}' does NOT end with '0'.")

        subs_row = self._db.query_one(
            "SELECT ACC_NBR, ACCT_ID, CUST_ID FROM subs WHERE acc_nbr = :1",
            [msisdn])
        if not subs_row:
            raise BusinessRuleError(f"No record found in 'subs' for MSISDN {msisdn}")

        acct_id, cust_id = subs_row[1], subs_row[2]

        acct_row = self._db.query_one(
            "SELECT ACCT_NAME, ACCT_NBR FROM acct WHERE ACCT_ID = :1", [acct_id])
        cust_row = self._db.query_one(
            "SELECT CUST_NAME, CUST_CODE FROM cust WHERE cust_id = :1", [cust_id])
        crm_row = self._db.query_one(
            "SELECT ACC_NBR_ID FROM crm.acc_nbr WHERE ACC_NBR = :1", [msisdn])

        return MsisdnInfo(
            msisdn=msisdn,
            acct_id=str(acct_id),
            acct_name=acct_row[0] if acct_row else None,
            acct_nbr=acct_row[1] if acct_row else None,
            cust_name=cust_row[0] if cust_row else None,
            cust_code=cust_row[1] if cust_row else None,
            acc_nbr_id=str(crm_row[0]) if crm_row else None,
            new_msisdn=msisdn[:-1]
        )

    def remove_trailing_zero(self, info: MsisdnInfo):
        """Rename MSISDN in subs, crm.acc_nbr and cc.acc_nbr (single commit)."""
        old, new = info.msisdn, info.new_msisdn

        self._db.execute(
            "UPDATE subs SET acc_nbr = :1 WHERE acc_nbr = :2", [new, old])

        if info.acc_nbr_id:
            self._db.execute(
                "UPDATE crm.acc_nbr SET acc_nbr = :1 "
                "WHERE acc_nbr = :2 AND ACC_NBR_ID = :3",
                [new, old, info.acc_nbr_id])
        else:
            self._db.execute(
                "UPDATE crm.acc_nbr SET acc_nbr = :1 WHERE acc_nbr = :2", [new, old])
