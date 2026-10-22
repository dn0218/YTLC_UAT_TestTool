"""Tab package."""
from ui.tabs.invoice_tab import InvoiceTab
from ui.tabs.contract_tab import ContractTab
from ui.tabs.msisdn_tab import MsisdnTab
from ui.tabs.sales_invoice_tab import SalesInvoiceTab
from ui.tabs.sim_card_tab import SimCardTab
from ui.tabs.roaming_tab import RoamingTab

__all__ = ["InvoiceTab", "ContractTab", "MsisdnTab", "SalesInvoiceTab",
           "SimCardTab", "RoamingTab"]
