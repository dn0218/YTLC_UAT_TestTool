"""Tab 6 UI - Roaming subscription pass (mdbtt asyn_call insert via SSH)."""
from tkinter import ttk

from ui.base_tab import BaseTab
from ui.widgets import ConsoleWidget

COUNTRIES = ("IRAN", "KENYA")


class RoamingTab(BaseTab):
    title = "Roaming Subscription Pass"

    def __init__(self, parent, ctx):
        super().__init__(parent, ctx)
        self._subs_rows = None   # raw rows from subs
        self._subs_ids = None    # resolved SUBS_ID strings

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def build(self):
        frame = ttk.LabelFrame(self, text=" Roaming Subscription Pass ")
        frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(frame, text="MSISDN:").grid(
            row=0, column=0, padx=8, pady=8, sticky="w")
        self.msisdn_entry = ttk.Entry(frame, width=32)
        self.msisdn_entry.grid(row=0, column=1, padx=8, pady=8, sticky="w")
        self.msisdn_entry.bind("<Return>", lambda ev: self.on_validate())

        self.btn_validate = ttk.Button(frame, text="Validate MSISDN",
                                       command=self.on_validate)
        self.btn_validate.grid(row=0, column=2, padx=8, pady=8)

        ttk.Label(frame, text="Country:").grid(
            row=1, column=0, padx=8, pady=8, sticky="w")
        self.country_var = ttk.Combobox(
            frame, values=list(COUNTRIES), state="readonly", width=29)
        self.country_var.current(COUNTRIES.index("KENYA"))
        self.country_var.grid(row=1, column=1, padx=8, pady=8, sticky="w")

        self.btn_run = ttk.Button(frame, text="Execute in mdbtt",
                                  state="disabled",
                                  command=self.on_execute,
                                  style="Success.TButton")
        self.btn_run.grid(row=1, column=2, padx=8, pady=8)

        frame_log = ttk.LabelFrame(self, text=" Operation Log ")
        frame_log.pack(fill="both", expand=True, padx=5, pady=10)
        self.console = ConsoleWidget(frame_log)
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
            self.bridge.run_on_ui(self.btn_run.configure, state="disabled")
            subs_ids, rows = self.ctx.roaming.get_subs_ids_by_msisdn(msisdn)
            self._subs_ids = subs_ids
            self._subs_rows = rows

            text = "--- MSISDN Validation Passed ---\n"
            text += f"MSISDN      : {msisdn}\n"
            text += f"Subscription(s) found: {len(subs_ids)}\n\n"
            for r in rows:
                text += (f"  SUBS_ID={r[0]}  acct_id={r[1]}  "
                         f"cust_id={r[2]}  created={r[3]}\n")
            text += "\nCountry AVP summary:\n"
            text += "  KENYA : 1463=03 | 1464=639  | 1465=10502\n"
            text += "  IRAN  : 1463=35 | 1464=432 | 1465=10240\n"
            self._log(text, clear=True)
            self.bridge.run_on_ui(self.btn_run.configure, state="normal")
        except Exception as e:
            self._subs_ids = None
            self.bridge.run_on_ui(self.btn_run.configure, state="disabled")
            self.handle_error(e, "Validation Failed")

    def on_execute(self):
        if not self._subs_ids:
            self.bridge.show_warning(
                "Missing Data", "Please validate the MSISDN first.")
            return
        country = self.country_var.get()
        msisdn = self.msisdn_entry.get().strip()
        subs = list(self._subs_ids)
        ok = self.bridge.ask_yes_no(
            "Confirm",
            f"Insert roaming pass row(s) for country {country}?\n\n"
            f"MSISDN : {msisdn}\n"
            f"SUBS_ID(s): {', '.join(subs)}\n\n"
            "This will run inside the OCS mdbtt SQL console "
            "(asyn_call insert, EVENT_ID=2, STATE='A').")
        if not ok:
            return
        self.run_worker(self._do_execute, subs, country, msisdn)

    def _do_execute(self, subs_ids, country, msisdn):
        try:
            self.bridge.run_on_ui(self.btn_run.configure, state="disabled")
            self._log(f"\n--- Roaming pass [{country}] for {msisdn} ---")

            def _confirm(_country, _subs):
                return True  # already confirmed in the UI above

            ok, done, failed = self.ctx.roaming.run_mdbtt_inserts(
                subs_ids, country,
                on_log=lambda l: self._log(l),
                confirm=_confirm)

            if ok:
                self._log(f"\nSUCCESS: {len(done)} asyn_call row(s) "
                          "inserted via mdbtt and committed.")
                self.bridge.show_info(
                    "Success",
                    f"Roaming pass rows inserted for {len(done)} "
                    "subscription(s).")
            else:
                self._log(f"\nFAILED for SUBS_ID(s): {', '.join(failed)}")
                self.bridge.show_error(
                    "Execution Failed",
                    f"Insert failed for SUBS_ID(s): {', '.join(failed)}. "
                    "Check the operation log.")
        except Exception as e:
            self.handle_error(e, "mdbtt Execution Error")
        finally:
            self.bridge.run_on_ui(self.btn_run.configure, state="normal")
