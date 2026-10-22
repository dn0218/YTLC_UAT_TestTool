"""Tab 5 UI - SIM Card Attribute (query ICCID, edit EXP_SIM_PRODUCT_TYPE)."""
import tkinter as tk
from tkinter import ttk, messagebox

from ui.base_tab import BaseTab
from ui.widgets import ConsoleWidget

ATTR_FILTER_CODE = "EXP_SIM_PRODUCT_TYPE"


class SimCardTab(BaseTab):
    title = "SIM Card Attribute"

    def __init__(self, parent, ctx):
        super().__init__(parent, ctx)
        self.sim_id = None
        self.card = {}
        self.attrs = []

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def build(self):
        top = ttk.LabelFrame(self, text=" ICCID Query ")
        top.pack(fill="x", padx=5, pady=5)

        ttk.Label(top, text="ICCID:").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.iccid_var = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.iccid_var, width=34,
                      font=("Consolas", 11))
        e.grid(row=0, column=1, padx=8, pady=8, sticky="w")
        e.bind("<Return>", lambda ev: self.on_query())
        self.btn_query = ttk.Button(top, text="Query", command=self.on_query)
        self.btn_query.grid(row=0, column=2, padx=8, pady=8)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(top, textvariable=self.status_var,
                  foreground="#1677ff").grid(row=0, column=3, padx=12, pady=8, sticky="w")

        info = ttk.LabelFrame(self, text=" Card Info ")
        info.pack(fill="x", padx=5, pady=5)
        self.info_var = tk.StringVar(value="(Enter an ICCID and click Query)")
        ttk.Label(info, textvariable=self.info_var,
                  justify=tk.LEFT).pack(anchor="w", padx=4, pady=4)

        attrf = ttk.LabelFrame(
            self, text=f" Attributes (only {ATTR_FILTER_CODE}, "
                       f"double-click a row to edit) ")
        attrf.pack(fill="both", expand=True, padx=5, pady=5)
        cols = ("no", "code", "name", "value")
        self.tree = ttk.Treeview(attrf, columns=cols, show="headings", height=8)
        for cid, text, w, an in (("no", "No.", 50, "center"),
                                 ("code", "ATTR_CODE", 150, "w"),
                                 ("name", "ATTR_NAME", 150, "w"),
                                 ("value", "ATTR_VALUE", 330, "w")):
            self.tree.heading(cid, text=text)
            self.tree.column(cid, width=w, anchor=an)
        self.tree.bind("<Double-1>", lambda ev: self.on_edit())
        vsb = ttk.Scrollbar(attrf, orient="vertical", command=self.tree.yview)
        self.tree.config(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        btnbar = ttk.Frame(self)
        btnbar.pack(fill="x", padx=5, pady=(0, 4))
        self.btn_edit = ttk.Button(btnbar, text="Edit Selected",
                                   command=self.on_edit)
        self.btn_edit.pack(side="left")
        self.btn_refresh = ttk.Button(btnbar, text="Refresh",
                                      command=self.on_query)
        self.btn_refresh.pack(side="left", padx=6)

        logf = ttk.LabelFrame(self, text=" Operation Log ")
        logf.pack(fill="both", padx=5, pady=(4, 8))
        self.console = ConsoleWidget(logf)
        self.console.configure(height=6)
        self.console.pack(fill="both", expand=True, padx=4, pady=4)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _log(self, msg):
        self.bridge.log(self.console, msg)

    def _render_info(self):
        parts = [f"{k}: {v}" for k, v in self.card.items() if v][:8]
        self.info_var.set("\n".join(parts) if parts else "(none)")

    def _render_attrs(self):
        self.tree.delete(*self.tree.get_children())
        for i, a in enumerate(self.attrs):
            self.tree.insert("", "end", iid=str(i),
                             values=(i + 1, a["code"], a["name"], a["value"]))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def on_query(self):
        iccid = self.iccid_var.get().strip()
        if not iccid:
            self.bridge.show_warning("Notice", "Please enter an ICCID")
            return
        self.btn_query.configure(state="disabled")
        self.status_var.set("Querying...")
        self.run_worker(self._do_query, iccid)

    def _do_query(self, iccid):
        try:
            sim_id, card = self.ctx.sim_cards.query_card(iccid)
            if sim_id is None:
                self.tree.delete(*self.tree.get_children())
                self._log(f"No SIM card found for ICCID={iccid}")
                self.bridge.run_on_ui(self.status_var.set, "Not found")
                self.bridge.show_info(
                    "Not Found", f"No SIM card found for ICCID={iccid}")
                return

            attrs = self.ctx.sim_cards.query_attrs(sim_id)
            self.sim_id, self.card, self.attrs = sim_id, card, attrs

            self.bridge.run_on_ui(self._render_info)
            self.bridge.run_on_ui(self._render_attrs)
            self.bridge.run_on_ui(
                self.status_var.set, f"SIM_CARD_ID={sim_id}, {len(attrs)} rows")
            self._log(f"Query {iccid} OK: SIM_CARD_ID={sim_id}, "
                      f"{ATTR_FILTER_CODE}={len(attrs)} row(s)")
        except Exception as e:
            self.bridge.run_on_ui(self.status_var.set, "Query failed")
            self._log(f"\u2718 Query error: {e}")
            self.bridge.show_error("Database Error", str(e))
        finally:
            self.bridge.run_on_ui(self.btn_query.configure, state="normal")

    def on_edit(self):
        sel = self.tree.selection()
        if not sel:
            self.bridge.show_warning("Notice", "Please select a row first")
            return
        self._open_edit_dialog(self.attrs[int(sel[0])])

    def _open_edit_dialog(self, a):
        win = tk.Toplevel(self)
        win.title("Edit Attribute")
        win.geometry("430x240")
        win.resizable(False, False)
        win.grab_set()

        tk.Label(win, text=f"Attribute:  {a['code']} / {a['name']}",
                 font=("Segoe UI", 10, "bold"), fg="#1677ff").pack(
                     anchor="w", padx=16, pady=(14, 4))
        tk.Label(win, text=f"Current Value:  {a['value']}").pack(
            anchor="w", padx=16, pady=4)
        tk.Label(win, text="New Value(JAVA/NATIVE):").pack(
            anchor="w", padx=16, pady=(10, 2))
        var = tk.StringVar()
        ent = tk.Entry(win, textvariable=var, font=("Consolas", 11))
        ent.pack(fill="x", padx=16)
        ent.focus_set()

        btns = tk.Frame(win)
        btns.pack(pady=14)

        def _confirm():
            new_value = var.get().strip()
            if not new_value:
                messagebox.showwarning("Notice", "Please enter a new value",
                                       parent=win)
                return
            if new_value == a["value"]:
                messagebox.showwarning(
                    "Notice", "New value is the same as current value", parent=win)
                return
            if not messagebox.askyesno(
                    "Confirm",
                    f"Change [{a['code']}]\nfrom '{a['value']}' to '{new_value}' ?",
                    parent=win):
                return
            btn_ok.config(state="disabled")
            self.run_worker(self._do_update, a, new_value, win, btn_ok)

        win.bind("<Return>", lambda ev: _confirm())
        btn_ok = tk.Button(btns, text="Confirm", width=12, command=_confirm,
                           bg="#1677ff", fg="white")
        btn_ok.pack(side="left", padx=6)
        tk.Button(btns, text="Cancel", width=10,
                  command=win.destroy).pack(side="left", padx=6)

    def _do_update(self, a, new_value, win, btn_ok):
        try:
            verified = self.ctx.sim_cards.update_attr_value(a["rowid"], new_value)
            self._log(f"UPDATE crm.SIM_CARD_ATTR_VALUE SET attr_value='{new_value}' "
                      f"WHERE rowid='{a['rowid']}';")
            self._log(f"\u2714 Update committed, verified new value: {verified}")
            self.bridge.run_on_ui(win.destroy)
            self.bridge.run_on_ui(self.on_query)  # auto refresh (UI thread)
        except Exception as e:
            self._log(f"\u2718 Update failed: {e}")
            self.bridge.show_error("Update Failed", str(e))
            self.bridge.run_on_ui(btn_ok.config, state="normal")
