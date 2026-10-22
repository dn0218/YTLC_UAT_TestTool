"""Tab base class + application context passed to every tab."""
import threading
from tkinter import ttk, messagebox

from connections.db_client import OracleClient, CrmOracleClient
from connections.ssh_client import SSHClient
from connections.api_client import JobApiClient
from connections.redis_client import RedisCacheClient
from core.config import AppConfig
from services import (AccountService, InvoiceService, ContractService,
                      MsisdnService, SalesInvoiceService, SimCardService,
                      RoamingService)
from ui.threading_bridge import UIThreadBridge


class AppContext:
    """Shared application objects handed to every tab."""

    def __init__(self, root: ttk.Frame = None, config: AppConfig = None):
        self.config = config
        self.bridge = UIThreadBridge(root)

        # Connections (shared, lazy)
        self.db = OracleClient(config)
        self.crm_db = CrmOracleClient(config)
        self.ssh = SSHClient(config)
        self.api = JobApiClient(config)
        self.redis = RedisCacheClient(config)

        # Services
        self.accounts = AccountService(self.db)
        self.invoices = InvoiceService(self.db, self.ssh, accounts=self.accounts)
        self.contracts = ContractService(self.db, redis=self.redis)
        self.msisdn = MsisdnService(self.db)
        self.sales_invoices = SalesInvoiceService(self.api, db=self.db)
        self.sim_cards = SimCardService(self.crm_db)
        self.roaming = RoamingService(self.db, self.ssh)


class BaseTab(ttk.Frame):
    """Common behaviour for all feature tabs."""

    title = "Tab"

    def __init__(self, parent, ctx: AppContext):
        super().__init__(parent, padding=10)
        self.ctx = ctx
        self.bridge = ctx.bridge
        self.build()

    # ------------------------------------------------------------------
    # To be implemented by subclasses
    # ------------------------------------------------------------------
    def build(self):
        """Create the tab's widgets. Override in subclasses."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def run_worker(self, target, *args):
        """Run target(*args) in a daemon thread."""
        threading.Thread(target=target, args=args, daemon=True).start()

    def handle_error(self, error, prefix="Error"):
        """Report an exception to the user (safe from any thread)."""
        self.bridge.show_error(prefix, str(error))
