"""Grants.gov API source.

Uses the public Grants.gov search API (no key required):
  POST https://api.grants.gov/v1/api/search2

Search hits carry structured fields we can trust: agency, open/close
dates, opportunity number, assistance listings (CFDA), and status.
Award amounts live on the separate details endpoint, which is
best-effort: when it is unavailable the record ships without an amount
rather than with a guessed one.

Eligibility codes (Grants.gov applicant-type codes):
  11 = Nonprofit organizations having a 501(c)(3) status with the IRS
  12 = Nonprofit organizations that do not have a 501(c)(3) status
Each code must be queried separately; a combined value matches nothing.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional

import requests

from ..models import FundingAmount, GrantRecord

logger = logging.getLogger("grant_finder_v2.grantsgov")

API_URL = "https://api.grants.gov/v1/api/search2"
DETAILS_URL = "https://api.grants.gov/v1/api/fetchOpportunity"
DETAIL_PAGE = "https://www.grants.gov/search-results-detail/{id}"

ELIGIBILITY_LABELS = {
    "11": "Nonprofit organizations with 501(c)(3) status",
    "12": "Nonprofit organizations (501(c)(3) status not required)",
}

# Tech and community keywords relevant to the /nonprofit-grants audience:
# nonprofits looking to fund technology work.
KEYWORDS = [
    "technology",
    "digital equity",
    "broadband",
    "STEM education",
    "workforce development",
    "cybersecurity",
    "artificial intelligence",
    "data science",
    "community development",
    "education technology",
    "telehealth",
    "digital literacy",
    "distance learning",
    "rural development",
]

TECH_FOCUS_BY_KEYWORD = {
    "technology": ["technology"],
    "digital equity": ["digital inclusion"],
    "broadband": ["broadband", "digital inclusion"],
    "STEM education": ["STEM", "education"],
    "workforce development": ["workforce development"],
    "cybersecurity": ["cybersecurity"],
    "artificial intelligence": ["artificial intelligence"],
    "data science": ["data"],
    "community development": ["community development"],
    "education technology": ["education technology", "education"],
    "telehealth": ["telehealth", "telemedicine"],
    "digital literacy": ["digital literacy", "digital inclusion"],
    "distance learning": ["distance learning", "online learning"],
    "rural development": ["rural development", "rural"],
}


def search_opportunities(
    keyword: str,
    eligibility_code: str,
    rows: int = 50,
    session: Optional[requests.Session] = None,
) -> List[dict]:
    """One search2 call. Returns raw oppHits (may be empty on failure)."""
    http = session or requests.Session()
    payload = {
        "keyword": keyword,
        "oppStatuses": "posted|forecasted",
        "eligibilities": eligibility_code,
        "rows": rows,
        "startRecordNum": 0,
        "sortBy": "closeDate|asc",
    }
    try:
        resp = http.post(API_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("oppHits", []) or []
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Grants.gov search failed (%s / %s): %s", keyword, eligibility_code, exc)
        return []


def fetch_award_amount(opp_id: str, session: Optional[requests.Session] = None) -> Optional[FundingAmount]:
    """Best-effort award ceiling/floor from the details endpoint.

    Returns None whenever the endpoint is unavailable or the fields are
    absent. Amounts are never inferred from text.
    """
    http = session or requests.Session()
    try:
        resp = http.post(DETAILS_URL, json={"id": int(opp_id)}, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        synopsis = data.get("synopsis", {}) or {}
        ceiling = synopsis.get("awardCeiling")
        floor = synopsis.get("awardFloor")
        if ceiling in (None, "", "none"):
            return None
        ceiling_f = float(str(ceiling).replace(",", ""))
        floor_f = None
        if floor not in (None, "", "none"):
            floor_f = float(str(floor).replace(",", ""))
        amount = floor_f if floor_f else ceiling_f
        range_max = ceiling_f if floor_f and ceiling_f != floor_f else None
        return FundingAmount(amount=amount, range_max=range_max)
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.debug("Grants.gov details unavailable for %s: %s", opp_id, exc)
        return None


def title_matches_keyword(title: str, keyword: str) -> bool:
    """True when the query concept appears in the opportunity title.

    Grants.gov keyword search matches full text, so a genomics grant
    that mentions "data" once would otherwise count as a data grant.
    The title is the honest relevance signal.
    """
    t = f" {title.lower()} "
    stems = {
        "technology": ["technolog"],
        "digital equity": ["digital"],
        "broadband": ["broadband"],
        "STEM education": ["stem", "science", "engineering", "math"],
        "workforce development": ["workforce", "employment", "job"],
        "cybersecurity": ["cybersecurity", "cyber security", "security"],
        "artificial intelligence": ["artificial intelligence", " ai ", " ai)", "machine learning"],
        "data science": ["data"],
        "community development": ["community"],
        "education technology": ["education", "learning", "school", "student"],
        "telehealth": ["telehealth", "telemedicine", "health"],
        "digital literacy": ["digital", "literacy", "computer"],
        "distance learning": ["distance learning", "online learning", "virtual learning"],
        "rural development": ["rural"],
    }.get(keyword, [keyword.lower()])
    return any(stem in t for stem in stems)


def hit_to_record(hit: dict, keyword: str, eligibility_code: str, today: date) -> Optional[GrantRecord]:
    opp_id = str(hit.get("id", "")).strip()
    title = (hit.get("title") or "").strip()
    if not opp_id or not title:
        return None
    close_raw = hit.get("closeDate") or ""
    close = None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            from datetime import datetime

            close = datetime.strptime(close_raw, fmt).date()
            break
        except (ValueError, TypeError):
            continue
    if close is not None and close.year >= 2099:
        # Grants.gov uses 2099 as a placeholder for open-ended
        # opportunities; it is not a real deadline.
        close = None
    agency = (hit.get("agency") or hit.get("agencyCode") or "Federal agency").strip()
    cfda = ", ".join(hit.get("cfdaList") or [])
    number = (hit.get("number") or "").strip()
    description = f"Federal funding opportunity {number} from {agency}." if number else f"Federal funding opportunity from {agency}."
    if cfda:
        description += f" Assistance listing {cfda}."
    description += " Full details, award information, and application instructions are on the official Grants.gov listing."
    return GrantRecord(
        title=title,
        description=description,
        source_url=DETAIL_PAGE.format(id=opp_id),
        source_name="Grants.gov",
        application_url=DETAIL_PAGE.format(id=opp_id),
        deadline=close.strftime("%B %-d, %Y") if close else None,
        deadline_iso=close.isoformat() if close else None,
        eligibility=ELIGIBILITY_LABELS.get(eligibility_code),
        tech_focus=TECH_FOCUS_BY_KEYWORD.get(keyword, []),
        nonprofit_sector=[],
        relevance_score=0.9,
        found_date=today.isoformat(),
        source_api="grants.gov",
        source_id=f"grantsgov-{opp_id}",
        verified_at=today.isoformat(),
    )


def collect(rows_per_query: int = 50, fetch_amounts: bool = True, today: Optional[date] = None) -> List[GrantRecord]:
    today = today or date.today()
    session = requests.Session()
    by_id: Dict[str, GrantRecord] = {}
    for keyword in KEYWORDS:
        for code in ELIGIBILITY_LABELS:
            hits = search_opportunities(keyword, code, rows=rows_per_query, session=session)
            logger.info("grants.gov keyword=%s eligibility=%s hits=%d", keyword, code, len(hits))
            for hit in hits:
                rec = hit_to_record(hit, keyword, code, today)
                if rec is None:
                    continue
                if not title_matches_keyword(rec.title, keyword):
                    continue  # keyword matched body text only: not relevant
                existing = by_id.get(rec.source_id)
                if existing is None:
                    by_id[rec.source_id] = rec
                else:
                    # Merge: keep the union of tech focus + eligibility labels.
                    existing.tech_focus = sorted(set(existing.tech_focus) | set(rec.tech_focus))
                    if rec.eligibility and rec.eligibility not in (existing.eligibility or ""):
                        existing.eligibility = (
                            f"{existing.eligibility}; {rec.eligibility}" if existing.eligibility else rec.eligibility
                        )
    records = list(by_id.values())
    if fetch_amounts:
        enriched = 0
        for rec in records:
            amount = fetch_award_amount(rec.source_id.replace("grantsgov-", ""), session=session)
            if amount is not None:
                rec.funding_amount = amount
                enriched += 1
        logger.info("grants.gov award amounts enriched: %d/%d", enriched, len(records))
    return records
