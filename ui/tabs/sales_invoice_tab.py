"""Tab 4 UI - Sales Invoice triggering."""
from tkinter import ttk

from ui.base_tab import BaseTab
from ui.widgets import ConsoleWidget
from ui.theme import PRIMARY, SUCCESS


class SalesInvoiceTab(BaseTab):
    title = "Sales Invoice"

    def __init__(self, parent, ctx):
        super().__init__(parent, ctx)
        self._acct_id = None
        self._account = None          # AccountInfo

    def build(self):
        frame_top = ttk.LabelFrame(self, text=" Account & Invoice Type ")
        frame_top.pack(fill="x", padx=5, pady=5)

        ttk.Label(frame_top, text="Account ID / Number:").grid(
            row=0, column=0, padx=8, pady=8, sticky="w")
        self.acct_entry = ttk.Entry(frame_top, width=32)
        self.acct_entry.grid(row=0, column=1, padx=8, pady=8, sticky="w")

        self.btn_check = ttk.Button(frame_top, text="Check Account",
                                    command=self.on_check_account)
        self.btn_check.grid(row=0, column=2, padx=8, pady=8)

        self.lbl_type = ttk.Label(frame_top, text="Type: N/A",
                                  font=("Segoe UI", 9, "bold"))
        self.lbl_type.grid(row=0, column=3, padx=12, pady=8, sticky="w")

        ttk.Label(frame_top, text="Billing Cycle:").grid(
            row=1, column=0, padx=8, pady=8, sticky="w")
        self.cycle_combo = ttk.Combobox(frame_top, width=30, state="disabled")
        self.cycle_combo.grid(row=1, column=1, padx=8, pady=8, sticky="w")

        self.btn_trigger = ttk.Button(frame_top, text="Trigger Sales Invoice",
                                      state="disabled",
                                      command=self.on_trigger,
                                      style="Success.TButton")
        self.btn_trigger.grid(row=1, column=2, padx=8, pady=8)

        frame_log = ttk.LabelFrame(self, text=" Sales Invoice Console ")
        frame_log.pack(fill="both", expand=True, padx=5, pady=10)

        self.console = ConsoleWidget(frame_log)
        self.console.pack(fill="both", expand=True, padx=5, pady=5)

    def _log(self, text: str):
        self.bridge.log(self.console, text)

    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.btn_check.configure(state=state)
        if self._account is None and not busy:
            self.btn_trigger.configure(state="disabled")
        else:
            self.btn_trigger.configure(state=state)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def on_check_account(self):
        user_acct = self.acct_entry.get().strip()
        if not user_acct:
            self.bridge.show_warning("Input Error",
                                     "Please enter an Account ID or Account Number.")
            return
        self._set_busy(True)
        self.run_worker(self._do_check_account, user_acct)

    def _do_check_account(self, user_acct: str):
        try:
            acct_id = self.ctx.accounts.resolve_acct_id(user_acct)
            account = self.ctx.accounts.validate_active(acct_id)
            self._acct_id = acct_id
            self._account = account

            if account.postpaid:
                self.bridge.run_on_ui(
                    self.lbl_type.config, text="Type: POSTPAID", foreground=PRIMARY)
                result = self.ctx.accounts.get_billing_cycles(
                    account.billing_cycle_type_id)
                labels = [c.display_label for c in result.cycles]
                default_idx = self.ctx.accounts.default_cycle_index(result.cycles)

                def show_cycles():
                    self.cycle_combo['values'] = labels
                    self.cycle_combo.current(default_idx)
                    self.cycle_combo.config(state="readonly")

                self.bridge.run_on_ui(show_cycles)
            else:
                self.bridge.run_on_ui(
                    self.lbl_type.config, text="Type: PREPAID", foreground=SUCCESS)
                self.bridge.run_on_ui(self._show_prepaid_combo)

            self.bridge.run_on_ui(self._enable_after_check)
            kind = "Postpaid" if account.postpaid else "Prepaid"
            self._log(f"Account {acct_id} validated as {kind}.")

        except Exception as e:
            self.bridge.run_on_ui(self._set_busy, False)
            self.handle_error(e, "Account Check Failed")

    def _show_prepaid_combo(self):
        self.cycle_combo.set("N/A (Prepaid Account)")
        self.cycle_combo.config(state="disabled")

    def _enable_after_check(self):
        self._set_busy(False)
        self.btn_trigger.configure(state="normal")

    def on_trigger(self):
        self._set_busy(True)
        self.run_worker(self._do_trigger)

    def _do_trigger(self):
        try:
            response = self.ctx.sales_invoices.trigger(
                self._account, on_log=lambda m: self._log(m))
            if response.status_code == 200:
                self._log("SUCCESS: Sales Invoice API triggered successfully.")
                job_name, _ = self.ctx.sales_invoices.build_job(self._account)
                self.bridge.show_info(
                    "Success",
                    f"Sales Invoice job '{job_name}' triggered successfully!")
            else:
                self._log(f"WARNING: API responded with status {response.status_code}")
                self.bridge.show_warning(
                    "API Warning",
                    f"Job triggered with non-200 status: {response.status_code}")
        except Exception as e:
            self._log(f"ERROR: Failed to trigger Sales Invoice API: {e}")
            self.handle_error(e, "Execution Error")
        finally:
            self.bridge.run_on_ui(self._set_busy, False)
