"""Tab 2 UI - Contract End Date management."""
from tkinter import ttk

from ui.base_tab import BaseTab
from ui.widgets import ConsoleWidget


class ContractTab(BaseTab):
    title = "Contract End Date"

    def __init__(self, parent, ctx):
        super().__init__(parent, ctx)
        self._last_agreement = None

    def build(self):
        frame = ttk.LabelFrame(self, text=" Manage Contract / Subscription ")
        frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(frame, text="MSISDN:").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.msisdn_entry = ttk.Entry(frame, width=32)
        self.msisdn_entry.grid(row=0, column=1, padx=8, pady=8, sticky="w")

        self.btn_check = ttk.Button(frame, text="Check Agreement Status",
                                    command=self.on_check_status)
        self.btn_check.grid(row=0, column=2, padx=8, pady=8)

        ttk.Label(frame, text="Expiry Date (YYYY-MM-DD):").grid(
            row=1, column=0, padx=8, pady=8, sticky="w")
        self.date_entry = ttk.Entry(frame, width=32)
        self.date_entry.grid(row=1, column=1, padx=8, pady=8, sticky="w")

        self.btn_update = ttk.Button(frame, text="Update Expiry Date",
                                     command=self.on_update_date)
        self.btn_update.grid(row=1, column=2, padx=8, pady=8)

        self.btn_deactivate = ttk.Button(frame, text="Deactivate Contract",
                                         command=self.on_deactivate)
        self.btn_deactivate.grid(row=1, column=3, padx=8, pady=8)

        frame_log = ttk.LabelFrame(self, text=" Operations Console ")
        frame_log.pack(fill="both", expand=True, padx=5, pady=10)

        self.console = ConsoleWidget(frame_log)
        self.console.pack(fill="both", expand=True, padx=5, pady=5)

    def _log(self, text: str):
        self.bridge.log(self.console, text)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def on_check_status(self):
        msisdn = self.msisdn_entry.get().strip()
        if not msisdn:
            self.bridge.show_warning("Input Error", "Please enter MSISDN.")
            return
        self.run_worker(self._do_check_status, msisdn)

    def _do_check_status(self, msisdn: str):
        try:
            agreement = self.ctx.contracts.get_agreement(msisdn)
            self._last_agreement = agreement
            self.ctx.contracts.check_active_warnings(
                agreement, on_log=lambda m: self._log(m))

            self._log(f"\n--- Agreement Status for MSISDN: {msisdn} ---")
            self._log(f"Agreement Name          : {agreement.sa_name or 'N/A'}")
            self._log(f"Agreement Effective Date: {agreement.eff_date or 'N/A'}")
            self._log(f"Agreement Expiry Date   : {agreement.exp_date or 'N/A'}")
        except Exception as e:
            self.handle_error(e, "Query Error")

    def on_update_date(self):
        msisdn = self.msisdn_entry.get().strip()
        expiry = self.date_entry.get().strip()
        if not msisdn or not expiry:
            self.bridge.show_warning(
                "Input Error", "Please provide MSISDN and target Expiry Date.")
            return
        self.run_worker(self._do_update_date, msisdn, expiry)

    def _do_update_date(self, msisdn: str, expiry: str):
        try:
            agreement = self.ctx.contracts.get_agreement(msisdn)
            self.ctx.contracts.check_active_warnings(
                agreement, on_log=lambda m: self._log(m))
            self.ctx.contracts.update_expiry_date(agreement, expiry)
            self._log(f"SUCCESS: Contract end date updated to {expiry} "
                      f"for MSISDN: {msisdn}")

            # Invalidate the Redis cache AFTER the DB update succeeded.
            cache_ok, _ = self.ctx.contracts.invalidate_subs_cache(
                agreement, on_log=lambda m: self._log(m))
            if cache_ok:
                self.bridge.show_info("Success",
                                      "Contract end date updated successfully.")
            else:
                self.bridge.show_info(
                    "Success",
                    "Contract end date updated successfully.\n"
                    "(Warning: cache invalidation failed, please check Redis.)")
        except Exception as e:
            self.handle_error(e, "Update Error")

    def on_deactivate(self):
        msisdn = self.msisdn_entry.get().strip()
        if not msisdn:
            self.bridge.show_warning("Input Error", "Please enter MSISDN.")
            return
        self.run_worker(self._do_deactivate, msisdn)

    def _do_deactivate(self, msisdn: str):
        try:
            agreement = self.ctx.contracts.get_agreement(msisdn)
            self.ctx.contracts.check_active_warnings(
                agreement, on_log=lambda m: self._log(m))
            deactivated_at = self.ctx.contracts.deactivate(agreement)
            self._log(f"SUCCESS: Deactivated contract ({deactivated_at}) "
                      f"for MSISDN: {msisdn}")

            # Invalidate the Redis cache AFTER the DB update succeeded.
            cache_ok, _ = self.ctx.contracts.invalidate_subs_cache(
                agreement, on_log=lambda m: self._log(m))
            if cache_ok:
                self.bridge.show_info("Success",
                                      "Contract deactivated successfully.")
            else:
                self.bridge.show_info(
                    "Success",
                    "Contract deactivated successfully.\n"
                    "(Warning: cache invalidation failed, please check Redis.)")
        except Exception as e:
            self.handle_error(e, "Deactivation Error")
