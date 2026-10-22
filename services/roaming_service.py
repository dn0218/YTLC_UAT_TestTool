"""Core 6 - Roaming subscription pass: push AVP config via OCS mdbtt console.

Business flow
-------------
1. Look up the MSISDN in OCS `subs` and collect EVERY SUBS_ID bound to it
   (a number may have several subscriptions, e.g. after a number change).
2. Let the user pick a roaming country (IRAN / KENYA).
3. For each SUBS_ID, insert one row into OCS `asyn_call` through the
   interactive `mdbtt` SQL console on the OCS SSH host (NOT via the
   direct cc Oracle connection - asyn_call writes must go through the
   OCS-side platform, same host/path as the Invoice Generation module).

The AVP payload only differs in the country-specific fields:
    1463 = country code part (03=KENYA, 35=IRAN)
    1464 = 639 (KENYA) / 432 (IRAN)
    1465 = 10502 (KENYA) / 10240 (IRAN)
"""
import time

from connections.db_client import OracleClient
from connections.ssh_client import SSHClient
from core.errors import BusinessRuleError

# Country -> AVP payload (identical structure, only country fields differ).
ROAMING_AVP = {
    "KENYA": ("965=6291456,11535056|987=110115702|982=12345|1462=+0800"
              "|1463=03|1464=639|1465=10502|1466=20260204"),
    "IRAN": ("965=6291456,11535056|987=110115702|982=12345|1462=+0800"
             "|1463=35|1464=432|1465=10240|1466=20260204"),
}

# mdbtt SQL-console prompt markers (ZSmart_QMDB direct mode).
PROMPT_SQL = "SQL>>"

_INSERT_SQL = (
    "insert into asyn_call (ASYN_CAL_ID, SUBS_ID, AVP, EVENT_ID, "
    "CREATED_DATE, STATE, STATE_DATE, COMMENTS, PRIORITY) values "
    "(asyn_call_id_seq.nextval, {subs_id}, '{avp}', 2, SYSDATE, 'A', "
    "SYSDATE, null, 500)"
)


class RoamingService:
    """Resolve SUBS_IDs for an MSISDN and run the mdbtt insert flow."""

    def __init__(self, db: OracleClient, ssh: SSHClient):
        self._db = db
        self._ssh = ssh

    # ------------------------------------------------------------------
    # Step 1 - MSISDN existence + SUBS_ID resolution
    # ------------------------------------------------------------------
    def get_subs_ids_by_msisdn(self, msisdn: str):
        """Return every SUBS_ID bound to the MSISDN (there may be several).

        Mirrors the existence check used by the "MSISDN Clean '0'" module
        (SELECT ... FROM subs WHERE acc_nbr = :msisdn).
        """
        msisdn = (msisdn or "").strip()
        if not msisdn:
            raise BusinessRuleError("Please enter an MSISDN.")

        # NOTE: CC.SUBS has no state/eff/exp columns (verified against
        # all_tab_columns) - only subs_id / acc_nbr / acct_id / cust_id /...
        rows = self._db.query_all(
            "SELECT s.subs_id, s.acct_id, s.cust_id, s.created_date "
            "FROM subs s WHERE s.acc_nbr = :1 ORDER BY s.subs_id",
            [msisdn])
        if not rows:
            raise BusinessRuleError(
                f"No record found in 'subs' for MSISDN {msisdn}")
        return [str(r[0]) for r in rows], rows

    # ------------------------------------------------------------------
    # Step 2/3 - build the country-specific insert SQL
    # ------------------------------------------------------------------
    @staticmethod
    def build_insert_sql(subs_id: str, country: str) -> str:
        try:
            avp = ROAMING_AVP[country]
        except KeyError:
            raise BusinessRuleError(
                f"Unsupported country '{country}' "
                f"(choose from: {', '.join(sorted(ROAMING_AVP))}).") from None
        return _INSERT_SQL.format(subs_id=subs_id, avp=avp)

    # ------------------------------------------------------------------
    # Step 4/5 - drive the mdbtt SQL console over SSH
    # ------------------------------------------------------------------
    def run_mdbtt_inserts(self, subs_ids, country, on_log=None,
                          confirm=None):
        """Open mdbtt on the OCS host and run one insert per SUBS_ID.

        on_log(line) receives every meaningful console line for the UI.
        confirm(country, subs_ids) -> bool lets the UI ask the user before
        the first statement is submitted (returns False aborts).
        Returns (ok: bool, done_subs: list, failed_subs: list).
        """
        def log(msg):
            if on_log:
                on_log(msg)

        if country not in ROAMING_AVP:
            raise BusinessRuleError(f"Unsupported country '{country}'.")
        if not subs_ids:
            raise BusinessRuleError("No SUBS_ID(s) to process.")

        if confirm is not None and not confirm(country, subs_ids):
            log("Aborted by user - nothing was executed in mdbtt.")
            return False, [], list(subs_ids)

        # mdbtt is started from the same directory as the invoice scripts
        # (cd invoicing/), per the Invoice Generation module's convention.
        chan = self._ssh.open_interactive_shell()
        ok_subs, failed_subs = [], []
        try:
            # -- wait for the plain shell prompt, then start mdbtt -------
            match, out = self._ssh.read_until(
                ["> ", "$ ", "# "], timeout=15, on_line=None)
            log(f"[ssh] shell ready, starting mdbtt ...")

            self._ssh.send_line("cd invoicing/")
            match, _ = self._ssh.read_until(
                ["> ", "$ ", "# "], timeout=15)

            self._ssh.send_line("mdbtt")
            match, out = self._ssh.read_until(
                [PROMPT_SQL], timeout=60,
                on_line=lambda l: log(f"[mdbtt] {l}"))
            if match != PROMPT_SQL:
                log("ERROR: mdbtt SQL prompt not detected. Console output:")
                for l in out.splitlines()[-12:]:
                    log(f"    {l}")
                return False, ok_subs, list(subs_ids)
            log("[mdbtt] SQL console ready (Direct mode).")

            # -- run one insert per SUBS_ID ------------------------------
            for idx, subs_id in enumerate(subs_ids, 1):
                sql = self.build_insert_sql(subs_id, country)
                log(f"[mdbtt] ({idx}/{len(subs_ids)}) SUBS_ID {subs_id}: "
                    "submitting insert ...")
                # NOTE: the mdbtt SQL console requires an explicit ';' to
                # execute - without it the console just waits for more input
                # (continuation prompts '  2   3 ') and never returns.
                self._ssh.send_line(sql + ";")
                match, out = self._ssh.read_until(
                    [PROMPT_SQL, "ERROR", "error", "ORA-"], timeout=60,
                    on_line=lambda l: log(f"[mdbtt] {l}"))
                if match == PROMPT_SQL:
                    ok_subs.append(subs_id)
                    log(f"[mdbtt] SUBS_ID {subs_id}: insert submitted OK.")
                else:
                    failed_subs.append(subs_id)
                    log(f"[mdbtt] SUBS_ID {subs_id}: FAILED (matched "
                        f"'{match}'). See console output above.")

            # -- commit, settle, then disconnect -----------------------
            self._ssh.send_line("commit;")
            self._ssh.read_until([PROMPT_SQL], timeout=30,
                                 on_line=lambda l: log(f"[mdbtt] {l}"))
            # Let the OCS platform settle (async processing of the queued
            # asyn_call rows) before tearing the SQL console down.
            log("[mdbtt] commit done; waiting 10s before disconnecting "
                "the SQL console ...")
            time.sleep(10)
            self._ssh.send_line("quit;")
            time.sleep(3)
            log("[mdbtt] SQL console disconnected (quit;); closing SSH session.")
        finally:
            self._ssh.close_interactive_shell()

        return (not failed_subs), ok_subs, failed_subs
