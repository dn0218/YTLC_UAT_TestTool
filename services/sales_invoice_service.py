"""Core 4 - Sales invoice job triggering via the job-server REST API."""
from datetime import datetime

from connections.api_client import JobApiClient
from connections.db_client import OracleClient
from core.models import AccountInfo


class SalesInvoiceService:
    """Trigger prepaid / postpaid sales e-invoice generation jobs."""

    def __init__(self, api: JobApiClient, db: OracleClient = None):
        self._api = api
        self._db = db

    def build_job(self, account: AccountInfo):
        """Return (job_name, params) for the given account type."""
        current_date = datetime.now().strftime("%Y-%m-%d")
        if account.postpaid:
            return ("PostpaidSalesEInvoiceGenerate",
                    f"POSTPAID_SALES_E_INVOICE,SRC_SUBS_EVENT_ID=1|SP_ID=101|"
                    f"QRY_DATE={current_date}")
        return ("PrepaidSalesEInvoiceGenerate",
                f"PREPAID_SALES_E_INVOICE,SP_ID=101|QRY_DATE={current_date}")

    def update_send_date(self, acct_id: str, on_log=None):
        """After a successful trigger, move SEND_DATE back one day on the
        account's sales-type e-invoices so they can be re-processed.

        Sales-type rows are identified by BILLING_CYCLE_ID IS NULL
        (postpaid/prepaid billing invoices always carry a cycle id).
        Best-effort: failures are logged, never raised.
        """
        if self._db is None:
            return 0
        try:
            updated = self._db.execute(
                "UPDATE e_invoice SET SEND_DATE = sysdate-1 "
                "WHERE ACCT_ID = :1 AND BILLING_CYCLE_ID IS NULL",
                [acct_id])
            if on_log:
                on_log(f"SEND_DATE updated (sysdate-1) on {updated} sales-type "
                       f"e_invoice row(s) for account {acct_id}.")
            return updated
        except Exception as e:
            if on_log:
                on_log(f"WARNING: failed to update SEND_DATE for account "
                       f"{acct_id}: {e}")
            return -1

    def trigger(self, account: AccountInfo, on_log=None):
        """Trigger the appropriate job; returns the requests.Response."""
        def log(msg):
            if on_log:
                on_log(msg)

        job_name, params = self.build_job(account)
        kind = "Postpaid" if account.postpaid else "Prepaid"
        log(f"--- Initiating Sales Invoice Trigger ({kind}) ---")
        log(f"Job Name  : {job_name}")
        log(f"Parameters: {params}")
        response = self._api.trigger_job(job_name, params, on_log=on_log)
        # After a successful trigger, allow re-processing of the sales invoice.
        if response.status_code == 200:
            self.update_send_date(account.acct_id, on_log=on_log)
        return response
