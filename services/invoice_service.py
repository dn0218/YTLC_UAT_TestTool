"""Core 1 - Invoice generation: SSH bill run + DB verification."""
import time
import xml.dom.minidom

from connections.db_client import OracleClient
from connections.ssh_client import SSHClient
from core.models import BillRunResult, BillingCycle


class InvoiceService:
    """Drives the Brainless_Invoice.sh bill run and verifies results in DB."""

    def __init__(self, db: OracleClient, ssh: SSHClient, accounts=None):
        self._db = db
        self._ssh = ssh
        self._accounts = accounts

    # ------------------------------------------------------------------
    # Pre-billing: RecurrRate pre-charges + EVENT_RECURRING verification
    # ------------------------------------------------------------------
    def run_prebilling(self, acct_id: str, cycle, on_log=None) -> bool:
        """Run RecurrRate for every subs under the account, then verify rows.

        Returns True when every subs (incl. balance-sharing subs) has rows
        in EVENT_RECURRING_<cycle>@link2rb on the next cycle's begin date
        (or when the step is skipped due to missing data); False = missing
        pre-charges and the caller decides whether to continue (GUI asks
        the user instead of aborting).
        """
        def log(msg):
            if on_log:
                on_log(msg)

        # RecurrRate -d must be the NEXT cycle's begin date. For a cycle,
        # next_begin == this cycle's end_date (e.g. cycle 2969 / type 316:
        # CYCLE_END_DATE 2026-10-16 == next begin -> -d 20261016).
        next_begin_date = cycle.end_date
        if not acct_id or not next_begin_date:
            log("WARNING: missing account/cycle info; skipping pre-billing step.")
            return True

        yyyymmdd = next_begin_date.replace("-", "")
        log(f"Pre-billing: querying subscriptions under account {acct_id} ...")
        try:
            subs_ids = self._accounts.get_subs_ids(acct_id)
            share_ids = self._accounts.get_bal_share_subs_ids(acct_id)
            if share_ids:
                subs_ids = list(dict.fromkeys(list(subs_ids) + share_ids))
                log(f"Added {len(share_ids)} balance-sharing SUBS_ID(s) "
                    "(bal_share PAYMENT_FORCE='Y', bal_share_detail "
                    f"EXP_DATE IS NULL): {', '.join(share_ids)}")
        except Exception as e:
            log(f"WARNING: failed to query subs list ({e}); skipping pre-billing step.")
            return True

        if not subs_ids:
            log(f"WARNING: no subscriptions found under account {acct_id}; "
                "skipping pre-billing step.")
            return True

        # Skip check: subs that already have RecurrRate pre-charge rows do
        # not need pre-billing again. RecurrRate writes rows whose
        # EVENT_BEGIN_TIME is a whole day (TRUNC = midnight, derived from the
        # -d argument). Account-opening supplementary charges carry a real
        # (non-midnight) timestamp. NOTE: the ACCT_ITEM_TYPE_ID1 of
        # RecurrRate rows is NOT fixed (observed 12 on one cycle, 4311 on
        # another), so only the truncated-time test is reliable.
        already, need_precharge = [], []
        try:
            for subs_id in subs_ids:
                cnt = self._accounts.count_event_recurring(
                    billing_cycle_id=cycle.billing_cycle_id,
                    subs_id=subs_id, truncated_time=True,
                    on_date=next_begin_date)
                if cnt and cnt > 0:
                    already.append(subs_id)
                    log(f"SUBS_ID {subs_id} already pre-charged "
                        f"({cnt} RecurrRate row(s) with whole-day "
                        "EVENT_BEGIN_TIME), skip RecurrRate.")
                else:
                    need_precharge.append(subs_id)
        except Exception as e:
            log(f"WARNING: pre-charge skip check failed ({e}); "
                "will run RecurrRate for all subs.")
            need_precharge = list(subs_ids)

        if not need_precharge:
            log(f"All {len(already)} subscription(s) already pre-charged. "
                "Skipping RecurrRate, proceeding to Brainless_Invoice.sh ...")
            return True

        # Resolve the RecurrRate executable path.
        # Interactive SSH works because a LOGIN shell loads ~/.bash_profile
        # (its PATH contains the bin dir). exec_command is NOT a login shell,
        # so resolve the absolute path via `bash -lc which` first, falling
        # back to common bin/ locations.
        recurr_rate_path = None
        ld_library_path = None
        which_lines = []
        try:
            self._ssh.exec_command_stream(
                "bash -lc 'which RecurrRate; echo LD_LIBRARY_PATH=$LD_LIBRARY_PATH'",
                on_line=which_lines.append, is_meaningful=lambda l: True)
            for ln in which_lines:
                ln = ln.strip()
                if ln.startswith("/") and ln.endswith("RecurrRate"):
                    recurr_rate_path = ln
                elif ln.startswith("LD_LIBRARY_PATH="):
                    ld_library_path = ln.split("=", 1)[1]
        except Exception:
            recurr_rate_path = None

        if not recurr_rate_path:
            for cand in ("~/bin/RecurrRate", "~/invoicing/bin/RecurrRate"):
                try:
                    ls_lines = []
                    ls_status = self._ssh.exec_command_stream(
                        f"ls -l {cand}",
                        on_line=ls_lines.append, is_meaningful=lambda l: True)
                    ls_out = "\n".join(ls_lines).strip()
                    if ls_status == 0 and "No such file" not in ls_out:
                        recurr_rate_path = cand
                        break
                except Exception:
                    continue

        if not recurr_rate_path:
            log("ERROR: could not locate RecurrRate on the SSH host "
                "(tried login-shell PATH, ~/bin/, ~/invoicing/bin/). "
                "Please check where the binary lives.")
            return False
        log(f"RecurrRate executable resolved: {recurr_rate_path} "
            f"(LD_LIBRARY_PATH={ld_library_path or 'not set'})")

        for subs_id in need_precharge:
            # e.g. cycle 2969 / type 316 (end 2026-10-16):
            #   RecurrRate -t 316 -T -d 20261016 -e 1 -s <subs> -l 5
            # Run inside a LOGIN shell so ~/.bash_profile provides the full OCS
            # environment (PATH + LD_LIBRARY_PATH for liboffline_*.so) - exactly
            # like an interactive SSH session.
            cmd = (f"bash -lc 'cd invoicing/ && {recurr_rate_path} "
                   f"-t {cycle.cycle_type_id} -T -d {yyyymmdd} -e 1 -s {subs_id} -l 5'")
            log(f"Executing: {cmd}")
            all_lines = []

            def _recurr_on_line(line):
                all_lines.append(line)
                # RecurrRate is very verbose - keep only the begin/end markers.
                if "Program RecurrRate begin" in line or "Program RecurrRate end" in line:
                    log(line)

            try:
                exit_status = self._ssh.exec_command_stream(
                    cmd, on_line=_recurr_on_line, is_meaningful=lambda l: True)
                if exit_status != 0:
                    tail = "\n".join(all_lines[-15:])
                    log(f"WARNING: RecurrRate for SUBS_ID {subs_id} exited with "
                        f"status {exit_status}. Last output lines:\n{tail}")
            except Exception as e:
                log(f"WARNING: RecurrRate execution failed for SUBS_ID {subs_id}: {e}")

        # sleep 10 s, then verify
        log("Waiting 10 seconds for recurring events to persist...")
        time.sleep(10)

        event_table = f"EVENT_RECURRING_{cycle.billing_cycle_id}@link2rb"
        failed = []
        for subs_id in need_precharge:
            try:
                cnt = self._accounts.count_event_recurring(
                    billing_cycle_id=cycle.billing_cycle_id,
                    subs_id=subs_id, truncated_time=True,
                    on_date=next_begin_date)
            except Exception as e:
                log(f"WARNING: EVENT_RECURRING verification query failed: {e}.")
                return False
            if cnt and cnt > 0:
                log(f"Pre-billing verified: {cnt} row(s) in {event_table} "
                    f"for SUBS_ID {subs_id}.")
            else:
                failed.append(subs_id)
                log(f"WARNING: no rows in {event_table} for SUBS_ID {subs_id}.")

        if failed:
            # Do NOT abort here: report and let the user decide whether to
            # continue without pre-charges (the GUI asks; see invoice_tab).
            log(f"WARNING: Pre-billing verification FAILED for SUBS_ID(s): "
                f"{', '.join(failed)} - no RecurrRate rows on {next_begin_date}.")
            return False

        total = len(already) + len(need_precharge)
        log(f"Pre-billing OK for all {total} subscription(s) "
            f"({len(already)} skipped, {len(need_precharge)} pre-charged now). "
            "Proceeding to Brainless_Invoice.sh ...")
        return True

    # ------------------------------------------------------------------
    # Bill run over SSH
    # ------------------------------------------------------------------
    def run_bill_script(self, acct_id: str, billing_cycle_id: int, on_log=None):
        """Execute the remote bill-run script, streaming meaningful lines."""
        def log(msg):
            if on_log:
                on_log(msg)

        log(f"--- Starting Bill Run for Account {acct_id}, Cycle {billing_cycle_id} ---")
        command = f"cd invoicing/ && ./Brainless_Invoice.sh {billing_cycle_id} {acct_id}"
        exit_status = self._ssh.exec_command_stream(command, on_line=log)
        log("Bill Run Done! Proceeding to verify invoice records and content...")
        return exit_status

    # ------------------------------------------------------------------
    # E-Invoice verification
    # ------------------------------------------------------------------
    def fetch_e_invoice_nbr(self, acct_id: str, billing_cycle_id: int,
                            max_attempts: int = 5, wait_seconds: int = 15,
                            on_log=None) -> str:
        """Poll e_invoice for the generated invoice number."""
        def log(msg):
            if on_log:
                on_log(msg)

        sql = ("SELECT E_INVOICE_NBR FROM e_invoice "
               "WHERE acct_id=:1 AND billing_cycle_id=:2")
        for attempt in range(1, max_attempts + 1):
            log(f"Attempt {attempt}/{max_attempts} to fetch E_INVOICE_NBR...")
            row = self._db.query_one(sql, [acct_id, billing_cycle_id])
            if row and row[0]:
                return row[0]
            if attempt < max_attempts:
                time.sleep(wait_seconds)
        return None

    def mark_invoice_sent(self, acct_id: str, billing_cycle_id: int):
        """Shift SEND_DATE back one day so the send job can pick invoices up.

        Covers ALL e_invoice rows of the account (not just this cycle), so
        every pending invoice of the account gets re-processed.
        """
        return self._db.execute(
            "UPDATE e_invoice SET SEND_DATE=sysdate-1 WHERE acct_id=:1",
            [acct_id]
        )

    # ------------------------------------------------------------------
    # Bill content (BLOB) validation
    # ------------------------------------------------------------------
    def fetch_bill_content(self, acct_id: str, billing_cycle_id: int) -> str:
        """Read BILL_CONTENT from bill_data_<cycle>@link2rb and decode it."""
        bill_table = f"bill_data_{billing_cycle_id}@link2rb"
        sql = (f"SELECT ACCT_ID, BILLING_CYCLE_ID, BILL_CONTENT "
               f"FROM {bill_table} WHERE ACCT_ID = :1")
        row = self._db.query_one(sql, [acct_id])
        if not row:
            raise LookupError(
                f"No bill data record found in {bill_table} for ACCT_ID {acct_id}.")

        blob = row[2]
        raw = blob.read() if hasattr(blob, 'read') else blob
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8', errors='ignore')
        return raw

    @staticmethod
    def beautify_xml(raw_xml: str) -> str:
        try:
            return xml.dom.minidom.parseString(raw_xml).toprettyxml(indent="  ")
        except Exception:
            return raw_xml

    @staticmethod
    def contains_null(raw_xml: str) -> bool:
        return "null" in raw_xml.lower()

    def verify_bill(self, acct_id: str, billing_cycle_id: int,
                    on_log=None) -> BillRunResult:
        """Full post-run verification pipeline (after the 30 s wait)."""
        def log(msg):
            if on_log:
                on_log(msg)

        # 0. Cool-down before touching the DB (matches original tool behaviour)
        log("Waiting 30 seconds before checking database records...")
        time.sleep(30)

        # 1. E-Invoice number
        e_invoice_nbr = self.fetch_e_invoice_nbr(acct_id, billing_cycle_id,
                                                 on_log=on_log)
        if e_invoice_nbr:
            updated = self.mark_invoice_sent(acct_id, billing_cycle_id)
            log(f"Invoice <{e_invoice_nbr}> status updated in DB "
                f"(SEND_DATE=sysdate-1 applied to ALL {updated} e_invoice "
                f"row(s) of account {acct_id}).")
        else:
            log("WARNING: Failed to retrieve E_INVOICE_NBR after 5 attempts. "
                "Proceeding to bill data validation.")

        # 2. Bill content BLOB

        bill_table = f"bill_data_{billing_cycle_id}@link2rb"
        log(f"Checking bill data in table {bill_table}...")
        xml_content = self.fetch_bill_content(acct_id, billing_cycle_id)
        has_null = self.contains_null(xml_content)

        if has_null:
            log("[!] WARNING: 'NULL' value detected in BILL_CONTENT XML.")
        else:
            log("SUCCESS: BILL_CONTENT verified. No NULL values found.")

        return BillRunResult(
            ok=not has_null,
            e_invoice_nbr=e_invoice_nbr,
            bill_content_xml=xml_content,
            has_null=has_null,
            message="NULL values detected" if has_null else "Verified OK"
        )
