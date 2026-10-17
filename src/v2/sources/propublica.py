"""ProPublica Nonprofit Explorer source (IRS Form 990 data).

API (no key required):
  GET https://projects.propublica.org/nonprofits/api/v2/search.json
  GET https://projects.propublica.org/nonprofits/api/v2/organizations/{ein}.json

This is the "990" half of Grant Finder v2: instead of guessing which
organizations might fund nonprofits, list Arizona grantmaking
foundations straight from their IRS filings, with a link to the filing
record so a nonprofit can see who actually received grants.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

import requests

from ..models import FunderRecord

logger = logging.getLogger("grant_finder_v2.propublica")

SEARCH_URL = "https://projects.propublica.org/nonprofits/api/v2/search.json"
ORG_URL = "https://projects.propublica.org/nonprofits/api/v2/organizations/{ein}.json"
PROFILE_URL = "https://projects.propublica.org/nonprofits/organizations/{ein}"

GRANTMAKING_HINTS = ("foundation", "fund", "trust", "charities", "charitable")


def _is_grantmaking(org: dict) -> bool:
    name = (org.get("name") or "").lower()
    ntee = (org.get("ntee_code") or "").upper()
    # NTEE T = philanthropy / voluntarism / grantmaking foundations.
    return ntee.startswith("T") or any(h in name for h in GRANTMAKING_HINTS)


def _latest_filing(ein: str, session: requests.Session) -> tuple[Optional[int], Optional[float]]:
    """Return (latest filing year, total assets at end of that filing)."""
    try:
        resp = session.get(ORG_URL.format(ein=ein), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        filings = data.get("filings_with_data") or []
        if not filings:
            return None, None
        latest = max(filings, key=lambda f: f.get("tax_prd_yr") or 0)
        return latest.get("tax_prd_yr"), latest.get("totassetsend")
    except (requests.RequestException, ValueError) as exc:
        logger.debug("ProPublica org lookup failed for %s: %s", ein, exc)
        return None, None


def collect(max_funders: int = 20, today: Optional[date] = None) -> List[FunderRecord]:
    today = today or date.today()
    session = requests.Session()
    candidates: list[dict] = []
    for page in range(4):
        orgs = None
        for attempt in range(2):  # one retry: the API occasionally drops a connection
            try:
                resp = session.get(
                    SEARCH_URL,
                    params={"q": "foundation", "state[id]": "AZ", "page": page},
                    timeout=30,
                )
                resp.raise_for_status()
                orgs = resp.json().get("organizations") or []
                break
            except (requests.RequestException, ValueError) as exc:
                logger.warning("ProPublica search failed (page %d, attempt %d): %s", page, attempt + 1, exc)
        if orgs is None:
            break
        candidates.extend(o for o in orgs if _is_grantmaking(o))
        logger.info("propublica page=%d orgs=%d grantmaking_candidates=%d", page, len(orgs), len(candidates))
        if not orgs:
            break

    funders: List[FunderRecord] = []
    seen_eins: set[str] = set()
    for org in candidates:
        ein = str(org.get("ein") or "")
        if not ein or ein in seen_eins:
            continue
        seen_eins.add(ein)
        year, assets = _latest_filing(ein, session)
        if year is None:
            continue  # No 990 filing data: not verifiable, skip.
        funders.append(
            FunderRecord(
                name=org.get("name") or "",
                ein=org.get("strein") or ein,
                city=org.get("city") or "",
                state=org.get("state") or "AZ",
                ntee_code=org.get("ntee_code") or "",
                latest_filing_year=year,
                total_assets=assets,
                propublica_url=PROFILE_URL.format(ein=ein),
                verified_at=today.isoformat(),
            )
        )
    funders.sort(key=lambda f: f.total_assets or 0, reverse=True)
    return funders[:max_funders]
