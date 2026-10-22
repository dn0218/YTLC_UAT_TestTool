"""Tab 1 UI - Invoice Generation."""
import time

from tkinter import ttk

from core.models import BillingCycle, CycleQueryResult
from ui.base_tab import BaseTab
from ui.widgets import ConsoleWidget


class InvoiceTab(BaseTab):
    title = "Invoice Generation"

    def __init__(self, parent, ctx):
        super().__init__(parent, ctx)
        self.acct_id = None
        self.cycles = []            # List[BillingCycle]

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def build(self):
        frame_top = ttk.LabelFrame(self, text=" Account & Cycle Selection ")
        frame_top.pack(fill="x", padx=5, pady=5)

        ttk.Label(frame_top, text="Account ID / Number:").grid(
            row=0, column=0, padx=8, pady=8, sticky="w")
        self.acct_entry = ttk.Entry(frame_top, width=32)
        self.acct_entry.grid(row=0, column=1, padx=8, pady=8, sticky="w")

        self.btn_check = ttk.Button(frame_top, text="Check Account",
                                    command=self.on_check_account)
        self.btn_check.grid(row=0, column=2, padx=8, pady=8)

        ttk.Label(frame_top, text="Pick Billing Cycle:").grid(
            row=1, column=0, padx=8, pady=8, sticky="w")
        self.cycle_combo = ttk.Combobox(frame_top, width=30, state="disabled")
        self.cycle_combo.grid(row=1, column=1, padx=8, pady=8, sticky="w")

        self.btn_run = ttk.Button(frame_top, text="Run Bill & Generate Invoice",
                                  state="disabled", command=self.on_run_bill,
                                  style="Success.TButton")
        btn_run = self.btn_run
        btn_run.grid(row=1, column=2, padx=8, pady=8)

        self.lbl_current_cycle = ttk.Label(frame_top, text="Current cycle: N/A",
                                           style="Muted.TLabel")
        self.lbl_current_cycle.grid(row=1, column=3, padx=12, pady=8, sticky="w")

        frame_log = ttk.LabelFrame(self, text=" Bill Run Progress & Console ")
        frame_log.pack(fill="both", expand=True, padx=5, pady=10)

        self.console = ConsoleWidget(frame_log)
        self.console.pack(fill="both", expand=True, padx=5, pady=5)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _log(self, text: str):
        self.bridge.log(self.console, text)

    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.btn_check.configure(state=state)
        self.btn_run.configure(state=state if not busy or self.acct_id else "disabled")

    def _display_cycles(self, result: CycleQueryResult):
        self.cycles = result.cycles
        labels = [c.display_label for c in self.cycles]
        default_idx = 0
        for i, c in enumerate(self.cycles):
            if c.is_current:
                default_idx = i
                self.lbl_current_cycle.config(text=f"Current cycle: {c.period}")

        if result.current_cycle is None:
            self.lbl_current_cycle.config(text="Current cycle: None in range")

        self.cycle_combo['values'] = labels
        self.cycle_combo.current(default_idx)
        # 'readonly' = the user CAN open the drop-down and pick any other
        # cycle (typing is still blocked). The old code never re-enabled the
        # combo after Check Account, so the drop-down stayed unusable.
        self.cycle_combo.configure(state="readonly")
        self._set_busy(False)
        self.btn_run.configure(state="normal")

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
            self.ctx.accounts.validate_active_postpaid(acct_id)
            info = self.ctx.accounts.get_account_info(acct_id)
            result = self.ctx.accounts.get_billing_cycles(info.billing_cycle_type_id)

            self.acct_id = acct_id
            self.bridge.run_on_ui(self._display_cycles, result)
            self._log(f"Account validated successfully. ID: {acct_id}. "
                      f"Found {len(result.cycles)} billing cycles.")

        except Exception as e:
            self.bridge.run_on_ui(self._set_busy, False)
            self.handle_error(e, "Account Check Failed")

    def on_run_bill(self):
        selected = self.cycle_combo.get()
        idx = None
        for i, c in enumerate(self.cycles):
            if c.display_label == selected:
                idx = i
                break

        if idx is None:
            self.bridge.show_warning("Selection Error",
                                     "Please select a valid billing cycle.")
            return

        cycle = self.cycles[idx]
        if not cycle.is_current:
            ok = self.bridge.ask_yes_no(
                "Billing Cycle Warning",
                f"The selected cycle ({cycle.period}) is NOT the current billing "
                f"cycle.\n\nAre you sure you want to proceed with this bill run?",
                icon="warning"
            )
            if not ok:
                return

        self._set_busy(True)
        self.run_worker(self._do_run_bill, cycle)

    def _do_run_bill(self, cycle: BillingCycle):
        try:
            # 0) Pre-billing: RecurrRate pre-charges + EVENT_RECURRING verify
            pre_ok = self.ctx.invoices.run_prebilling(
                self.acct_id, cycle, on_log=lambda m: self._log(m))
            if not pre_ok:
                self._log("WARNING: recurring-event pre-billing verification "
                          "FAILED - no RecurrRate rows found in "
                          "EVENT_RECURRING_<cycle>@link2rb for some "
                          "subscription(s).")
                proceed = self.bridge.ask_yes_no(
                    "No Pre-charge Found",
                    "Recurring-rate pre-charge verification failed.\n\n"
                    "No rows found in EVENT_RECURRING_<cycle>@link2rb for some "
                    "subscription(s) after running RecurrRate.\n\n"
                    "The bill may be MISSING recurring charges.\n\n"
                    "Do you still want to continue the bill run "
                    "(Brainless_Invoice.sh)?",
                    icon="warning")
                if not proceed:
                    self._log("Bill Run ABORTED by user: bill NOT generated "
                              "(Brainless_Invoice.sh was NOT executed).")
                    self.bridge.show_warning(
                        "Bill Run Cancelled",
                        "Bill run cancelled - no pre-charge confirmed and "
                        "user chose not to continue.")
                    return
                self._log("User confirmed: continuing bill run WITHOUT verified "
                          "pre-charges ...")

            # 1) Remote bill run over SSH
            self.ctx.invoices.run_bill_script(
                self.acct_id, cycle.billing_cycle_id,
                on_log=lambda m: self._log(m))

            # 2) Verify invoice + bill content in DB
            result = self.ctx.invoices.verify_bill(
                self.acct_id, cycle.billing_cycle_id,
                on_log=lambda m: self._log(m))

            if result.has_null:
                pretty = self.ctx.invoices.beautify_xml(result.bill_content_xml)
                self._log("--------------------------------------------------")
                self._log(pretty)
                self._log("--------------------------------------------------")

                rerun = self.bridge.ask_yes_no(
                    "Null Value Detected",
                    f"Invoice generated (<{result.e_invoice_nbr or 'N/A'}>), but "
                    f"'NULL' content was found inside the BILL_CONTENT XML.\n\n"
                    f"Would you like to rerun the bill generation?"
                )
                if rerun:
                    self._log("User initiated bill rerun. Restarting execution...")
                    self._do_run_bill(cycle)
                    return
                self._log("User chose to skip rerun despite NULL detection.")
            else:
                self.bridge.show_info(
                    "Success",
                    f"Invoice <{result.e_invoice_nbr}> successfully generated "
                    f"and verified!")

        except LookupError as e:
            self._log(f"WARNING: {e}")
            self.bridge.show_warning("Bill Data Missing", str(e))
        except Exception as e:
            self._log(f"Error during execution: {e}")
            self.handle_error(e, "Execution Error")
        finally:
            self.bridge.run_on_ui(self._set_busy, False)
