"""Immutable data models passed between the business layer and the UI layer."""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass(frozen=True)
class BillingCycle:
    billing_cycle_id: int
    cycle_type_id: int
    begin_date: str          # 'YYYY-MM-DD'
    end_date: str            # 'YYYY-MM-DD'
    is_current: bool

    @property
    def period(self) -> str:
        return f"{self.begin_date} - {self.end_date}"

    @property
    def display_label(self) -> str:
        return f"[Current] {self.period}" if self.is_current else self.period


@dataclass(frozen=True)
class AccountInfo:
    acct_id: str
    state: str
    postpaid: bool
    billing_cycle_type_id: int
    acct_nbr: Optional[str] = None
    acct_name: Optional[str] = None


@dataclass(frozen=True)
class MsisdnInfo:
    msisdn: str
    acct_id: str
    acct_name: Optional[str]
    acct_nbr: Optional[str]
    cust_name: Optional[str]
    cust_code: Optional[str]
    acc_nbr_id: Optional[str]
    new_msisdn: str = field(default="")


@dataclass(frozen=True)
class AgreementInfo:
    prod_id: str
    prod_state: str
    eff_date: Optional[str]
    exp_date: Optional[str]
    agreement_id: Optional[str]
    sa_inst_id: Optional[str] = None
    sa_state: Optional[str] = None
    sa_name: Optional[str] = None


@dataclass(frozen=True)
class BillRunResult:
    ok: bool
    e_invoice_nbr: Optional[str]
    bill_content_xml: Optional[str]
    message: str = ""
    has_null: bool = False


@dataclass(frozen=True)
class CycleQueryResult:
    cycles: List[BillingCycle]

    @property
    def current_cycle(self) -> Optional[BillingCycle]:
        for c in self.cycles:
            if c.is_current:
                return c
        return None
