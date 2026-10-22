"""Tab 3 UI - Remove trailing '0' from MSISDN."""
from tkinter import ttk

from ui.base_tab import BaseTab
from ui.widgets import ConsoleWidget


class MsisdnTab(BaseTab):
    title = "MSISDN Clean '0'"

    def __init__(self, parent, ctx):
        super().__init__(parent, ctx)
        self._info = None

    def build(self):
        frame = ttk.LabelFrame(self, text=" Remove Trailing Zero from MSISDN ")
        frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(frame, text="MSISDN:").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.msisdn_entry = ttk.Entry(frame, width=32)
        self.msisdn_entry.grid(row=0, column=1, padx=8, pady=8, sticky="w")

        self.btn_validate = ttk.Button(frame, text="Validate MSISDN",
                                       command=self.on_validate)
        self.btn_validate.grid(row=0, column=2, padx=8, pady=8)

        self.btn_remove = ttk.Button(frame, text="Remove Last '0'",
                                     state="disabled",
                                     command=self.on_remove_zero,
                                     style="Success.TButton")
        self.btn_remove.grid(row=0, column=3, padx=8, pady=8)

        frame_info = ttk.LabelFrame(self, text=" Account & Customer Details ")
        frame_info.pack(fill="both", expand=True, padx=5, pady=10)

        self.console = ConsoleWidget(frame_info)
        self.console.pack(fill="both", expand=True, padx=5, pady=5)

    def _log(self, text: str, clear=False):
        if clear:
            self.bridge.run_on_ui(self.console.clear)
        self.bridge.log(self.console, text)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def on_validate(self):
        msisdn = self.msisdn_entry.get().strip()
        if not msisdn:
            self.bridge.show_warning("Input Error", "Please enter an MSISDN.")
            return
        self.run_worker(self._do_validate, msisdn)

    def _do_validate(self, msisdn: str):
        try:
            info = self.ctx.msisdn.validate(msisdn)
            self._info = info

            text = "--- MSISDN Validation Passed ---\n"
            text += f"Original MSISDN  : {info.msisdn}\n"
            text += f"New Target MSISDN: {info.new_msisdn}\n\n"
            text += f"Account Name     : {info.acct_name or 'N/A'}\n"
            text += f"Account Number   : {info.acct_nbr or 'N/A'}\n"
            text += f"Customer Name    : {info.cust_name or 'N/A'}\n"
            text += f"Customer Number  : {info.cust_code or 'N/A'}\n"
            text += f"CRM ACC_NBR_ID   : {info.acc_nbr_id or 'Not Found'}"

            self._log(text, clear=True)
            self.bridge.run_on_ui(self.btn_remove.configure, state="normal")
        except Exception as e:
            self.bridge.run_on_ui(self.btn_remove.configure, state="disabled")
            self.handle_error(e, "Validation Failed")

    def on_remove_zero(self):
        if not self._info:
            return
        info = self._info
        ok = self.bridge.ask_yes_no(
            "Confirm",
            f"Are you sure you want to change MSISDN from {info.msisdn} "
            f"to {info.new_msisdn}?"
        )
        if not ok:
            return
        self.run_worker(self._do_remove_zero, info)

    def _do_remove_zero(self, info):
        try:
            self.ctx.msisdn.remove_trailing_zero(info)
            self._log(f"\nSUCCESS: Updated MSISDN from '{info.msisdn}' to "
                      f"'{info.new_msisdn}' across all target tables.")
            self.bridge.show_info(
                "Success", f"MSISDN updated successfully to {info.new_msisdn}")
            self.bridge.run_on_ui(self.btn_remove.configure, state="disabled")
        except Exception as e:
            self.handle_error(e, "Update Error")
