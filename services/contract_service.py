"""Core 2 - Contract / agreement end-date management."""
from datetime import datetime, timedelta

from connections.db_client import OracleClient
from core.errors import BusinessRuleError
from core.models import AgreementInfo


class ContractService:
    """Query and update prod / subs_agreement_inst agreement dates."""

    def __init__(self, db: OracleClient, redis=None):
        self._db = db
        self._redis = redis

    def get_agreement(self, msisdn: str) -> AgreementInfo:
        """Join subs -> prod and fetch the agreement instance, if any."""
        sql1 = """
            SELECT p.PROD_ID, p.PROD_STATE,
                   TO_CHAR(p.AGREEMENT_EFF_DATE, 'YYYY-MM-DD HH24:MI:SS'),
                   TO_CHAR(p.AGREEMENT_EXP_DATE, 'YYYY-MM-DD HH24:MI:SS'),
                   p.AGREEMENT_ID
            FROM subs s
            JOIN prod p ON s.subs_id = p.prod_id
            WHERE s.ACC_NBR = :1
        """
        p_row = self._db.query_one(sql1, [msisdn])
        if not p_row:
            raise BusinessRuleError(f"No record found for MSISDN: {msisdn}")

        prod_id, prod_state, p_eff, p_exp, agreement_id = p_row

        sql2 = """
            SELECT SA.INST_ID,
                   TO_CHAR(SA.EFF_DATE, 'YYYY-MM-DD HH24:MI:SS'),
                   SA.STATE,
                   SA.AGREEMENT_NAME
            FROM subs_agreement_inst SA
            WHERE SA.INST_ID = :1 AND SA.AGREEMENT_ID = :2
        """
        sa_row = self._db.query_one(sql2, [prod_id, agreement_id])

        sa_state = sa_row[2] if sa_row else None
        sa_name = sa_row[3] if sa_row else None

        return AgreementInfo(
            prod_id=str(prod_id),
            prod_state=prod_state,
            eff_date=p_eff,
            exp_date=p_exp,
            agreement_id=str(agreement_id) if agreement_id is not None else None,
            sa_inst_id=str(sa_row[0]) if sa_row else None,
            sa_state=sa_state,
            sa_name=sa_name
        )

    @staticmethod
    def check_active_warnings(agreement: AgreementInfo, on_log=None):
        """Non-fatal state warnings, identical to the original tool."""
        if agreement.prod_state != 'A' and on_log:
            on_log(f"WARNING: product is not active (State={agreement.prod_state}), "
                   f"OK to proceed update.")
        if agreement.sa_state and agreement.sa_state != 'A' and on_log:
            on_log(f"WARNING: <{agreement.sa_name}> is not active "
                   f"(State={agreement.sa_state}), OK to proceed update.")

    def update_expiry_date(self, agreement: AgreementInfo, expiry_date: str):
        """Set exp dates on prod / subs_agreement_inst / cc.subs_agreement_inst.

        Note: also updates CC.SUBS_AGREEMENT_INST.EXP_DATE (same instance),
        because the CC-side view of the agreement must stay in sync.
        """
        try:
            self._db.execute(
                "UPDATE prod SET AGREEMENT_EXP_DATE = TO_DATE(:1, 'YYYY-MM-DD') "
                "WHERE prod_id = :2",
                [expiry_date, agreement.prod_id])
            self._db.execute(
                "UPDATE subs_agreement_inst SET EFF_DATE = TO_DATE(:1, 'YYYY-MM-DD') "
                "WHERE INST_ID = :2 AND AGREEMENT_ID = :3",
                [expiry_date, agreement.prod_id, agreement.agreement_id])
            self._db.execute(
                "UPDATE cc.subs_agreement_inst SET EXP_DATE = TO_DATE(:1, 'YYYY-MM-DD') "
                "WHERE INST_ID = :2 AND AGREEMENT_ID = :3",
                [expiry_date, agreement.prod_id, agreement.agreement_id])
        except Exception:
            self._db.execute(
                "UPDATE prod SET AGREEMENT_EXP_DATE = "
                "TO_TIMESTAMP(:1, 'YYYY-MM-DD HH24:MI:SS') WHERE prod_id = :2",
                [expiry_date, agreement.prod_id])
            self._db.execute(
                "UPDATE subs_agreement_inst SET EFF_DATE = "
                "TO_TIMESTAMP(:1, 'YYYY-MM-DD HH24:MI:SS') "
                "WHERE INST_ID = :2 AND AGREEMENT_ID = :3",
                [expiry_date, agreement.prod_id, agreement.agreement_id])

    def deactivate(self, agreement: AgreementInfo) -> str:
        """Expire the contract by setting dates to sysdate-1."""
        self._db.execute(
            "UPDATE prod SET AGREEMENT_EXP_DATE = sysdate-1 WHERE prod_id = :1",
            [agreement.prod_id])
        self._db.execute(
            "UPDATE subs_agreement_inst SET EFF_DATE = sysdate-1 "
            "WHERE INST_ID = :1 AND AGREEMENT_ID = :2",
            [agreement.prod_id, agreement.agreement_id])
        self._db.execute(
            "UPDATE cc.subs_agreement_inst SET EXP_DATE = sysdate-1 "
            "WHERE INST_ID = :1 AND AGREEMENT_ID = :2",
            [agreement.prod_id, agreement.agreement_id])
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    # Redis cache invalidation
    # ------------------------------------------------------------------
    SUBS_CACHE_KEY_TEMPLATE = "DUMP_SUBS_CACHE/ADAPTER_QRY_SUBS_INFO/{subs_id}"

    def invalidate_subs_cache(self, agreement: AgreementInfo, on_log=None):
        """Best-effort UNLINK of the subscription cache key after commit.

        Returns (True, key) on success, (False, error_message) on failure.
        Cache failure never fails the DB update.
        """
        key = self.SUBS_CACHE_KEY_TEMPLATE.format(subs_id=agreement.prod_id)
        ok, detail = self._redis.invalidate(key)
        if on_log:
            if ok:
                on_log(f"Cache invalidated: {detail}")
            else:
                on_log(f"WARNING: Failed to invalidate Redis cache for "
                       f"SUBS_ID <{agreement.prod_id}>: {detail}")
        return ok, detail
