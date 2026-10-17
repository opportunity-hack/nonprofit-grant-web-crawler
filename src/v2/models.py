"""Data models for Grant Finder v2.

The GrantRecord shape is a superset of the JSON contract the
/nonprofit-grants page on ohack.dev already renders (title, description,
source_name, funding_amount{amount,currency,range_max}, deadline,
application_url, eligibility), plus provenance fields the legacy
pipeline never kept (source_api, source_id, deadline_iso, verified_at).
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class FundingAmount(BaseModel):
    amount: float
    currency: str = "USD"
    range_max: Optional[float] = None


class GrantRecord(BaseModel):
    title: str
    description: str
    source_url: str
    source_name: str
    application_url: Optional[str] = None
    funding_amount: Optional[FundingAmount] = None
    # Human display string, e.g. "March 5, 2027". Rendered by the page.
    deadline: Optional[str] = None
    # Machine date, YYYY-MM-DD. The validator guarantees this is a real
    # parsed date and (for dated opportunities) not in the past.
    deadline_iso: Optional[str] = None
    eligibility: Optional[str] = None
    tech_focus: List[str] = Field(default_factory=list)
    nonprofit_sector: List[str] = Field(default_factory=list)
    volunteer_component: bool = False
    hackathon_eligible: bool = False
    remote_participation: Optional[bool] = None
    relevance_score: float = 0.0
    found_date: str = ""
    # Provenance (new in v2)
    source_api: str = ""
    source_id: str = ""
    verified_at: str = ""


class FunderRecord(BaseModel):
    """A grantmaking foundation from IRS Form 990 data (ProPublica)."""

    name: str
    ein: str
    city: str = ""
    state: str = "AZ"
    ntee_code: str = ""
    latest_filing_year: Optional[int] = None
    total_assets: Optional[float] = None
    propublica_url: str = ""
    source_api: str = "propublica"
    verified_at: str = ""
