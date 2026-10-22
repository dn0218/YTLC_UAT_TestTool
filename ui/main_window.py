"""Main application window: notebook, tabs, lifecycle management."""
import tkinter as tk
from tkinter import ttk, messagebox

from core.config import AppConfig
from core.errors import AppConfigError
from ui.base_tab import AppContext
from ui.tabs import (InvoiceTab, ContractTab, MsisdnTab, SalesInvoiceTab,
                     SimCardTab, RoamingTab)
from ui.theme import apply_theme


class MainWindow(tk.Tk):
    """Top-level window: owns config, context and tabs."""

    TAB_CLASSES = [InvoiceTab, ContractTab, MsisdnTab, SalesInvoiceTab,
                   SimCardTab, RoamingTab]

    def __init__(self):
        super().__init__()
        self.title("Telecom Operations Toolkit")
        self.geometry("1020x780")
        self.minsize(900, 700)

        self.ctx = None

        try:
            config = AppConfig()
        except AppConfigError as e:
            # Config may just have been created for the first time.
            messagebox.showinfo("Config", str(e))
            self.destroy()
            return

        apply_theme(self)
        self.ctx = AppContext(root=self, config=config)
        self._build_notebook()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_notebook(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        for tab_cls in self.TAB_CLASSES:
            tab = tab_cls(notebook, self.ctx)
            notebook.add(tab, text=tab.title)

    def _on_close(self):
        """Release remote resources before quitting."""
        try:
            if self.ctx:
                self.ctx.db.close()
                self.ctx.crm_db.close()
                self.ctx.ssh.close()
                self.ctx.redis.close()
        finally:
            self.destroy()
