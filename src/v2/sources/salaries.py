"""Salary benchmarking from IRS Form 990 Part VII (via ProPublica).

The 990 Data Finder problem statement asks for two datasets: grants
(covered by the other v2 sources) and salary information, so nonprofits
can offer competitive compensation. This module builds the salary half:

- Comparable set: Arizona nonprofits filing Form 990 with paid officers
  (ProPublica Nonprofit Explorer API, IRS data).
- Per-person detail: Part VII of the 990 XML (name is dropped; we keep
  title, hours, and reportable + other compensation) fetched from
  ProPublica's XML mirror of the IRS e-file data.
- Output: median / quartile total compensation per role bucket, split
  by organization revenue band, plus the individual records behind the
  numbers (all public filing data).

Only full-time signals are counted: a person enters the benchmarks when
their filing shows at least 20 average hours/week and at least $20,000
in total compensation. That removes unpaid board members and stipend
roles, which would otherwise drag every median toward zero.
"""

from __future__ import annotations

import io
import logging
import re
import statistics
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

import requests

logger = logging.getLogger("grant_finder_v2.salaries")

ORG_URL = "https://projects.propublica.org/nonprofits/api/v2/organizations/{ein}.json"
SEARCH_URL = "https://projects.propublica.org/nonprofits/api/v2/search.json"
XML_URL = "https://projects.propublica.org/nonprofits/download-xml?object_id={oid}"

MIN_HOURS = 20.0
MIN_COMP = 20_000
MIN_BUCKET_N = 4

ROLE_RULES: list[tuple[str, list[str]]] = [
    ("Executive Director / CEO", ["chief executive", "executive director", "president/ceo",
                                  "president & ceo", "president and ceo", " ceo", "ceo ",
                                  "executive dir", "president"]),
    ("Finance (CFO / Controller)", ["chief financial", "cfo", "finance", "controller",
                                    "accounting", "treasurer"]),
    ("Operations (COO)", ["chief operating", "coo", "operations"]),
    ("Development / Fundraising", ["development", "advancement", "fundraising", "philanthropy"]),
    ("Programs", ["program", "chief program", "education", "artistic", "curator",
                  "clinical", "medical director"]),
    ("Other Directors & Officers", ["chief", "vice president", "vp ", "director", "officer",
                                    "secretary", "manager"]),
]

REVENUE_BANDS = [
    ("Under $1M", 0, 1_000_000),
    ("$1M - $10M", 1_000_000, 10_000_000),
    ("$10M+", 10_000_000, float("inf")),
]

# Extra sub-band published alongside (not instead of) the bands above:
# very small organizations are the most-requested comparison and are
# otherwise hidden inside "Under $1M". A person under this ceiling
# still counts in "Under $1M" and "All sizes" exactly as before; the
# "Under $350K" rows are an additional cut of the same people.
EXTRA_REVENUE_BAND_LABEL = "Under $350K"
EXTRA_REVENUE_BAND_CEILING = 350_000


@dataclass
class PersonComp:
    org_name: str
    ein: str
    city: str
    revenue: Optional[float]
    filing_year: Optional[int]
    title_raw: str
    role: str
    hours: Optional[float]
    comp_total: float
    state: str = ""


def classify_role(title: str) -> str:
    t = f" {title.lower()} "
    for role, needles in ROLE_RULES:
        if any(n in t for n in needles):
            return role
    return "Other Directors & Officers"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(elem: ET.Element, name: str) -> Optional[str]:
    for child in elem:
        if _local(child.tag) == name:
            return (child.text or "").strip() or None
    return None


def _to_float(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _row_from_group(elem: ET.Element) -> dict:
    comp_org = _to_float(_child_text(elem, "ReportableCompFromOrgAmt")) or 0.0
    comp_rel = _to_float(_child_text(elem, "ReportableCompFromRltdOrgAmt")) or 0.0
    comp_other = _to_float(_child_text(elem, "OtherCompensationAmt")) or 0.0
    return {
        "title": _child_text(elem, "TitleTxt") or "",
        "hours": _to_float(_child_text(elem, "AverageHrsPerWkRt")),
        "comp_total": comp_org + comp_rel + comp_other,
    }


def parse_part_vii(xml_bytes: bytes) -> list[dict]:
    """Extract Part VII Section A rows from a Form 990 XML document.

    Tries a full XML parse first. If the document is truncated (large
    filings sometimes arrive incomplete through proxies), falls back to
    extracting each complete Part VII group with a regex: Part VII sits
    early in the return, so a partial prefix usually contains it whole.
    """
    try:
        root = ET.parse(io.BytesIO(xml_bytes)).getroot()
        return [_row_from_group(elem) for elem in root.iter()
                if _local(elem.tag) == "Form990PartVIISectionAGrp"]
    except ET.ParseError:
        rows: list[dict] = []
        for match in re.finditer(
            rb"<Form990PartVIISectionAGrp>(.*?)</Form990PartVIISectionAGrp>",
            xml_bytes, re.DOTALL,
        ):
            try:
                frag = ET.fromstring(b"<root>" + match.group(1) + b"</root>")
            except ET.ParseError:
                continue
            rows.append(_row_from_group(frag))
        return rows


def fetch_xml(object_id: str, session: requests.Session, attempts: int = 4) -> Optional[bytes]:
    """Download a filing XML, tolerating truncated transfers.

    ProPublica's download endpoint streams chunked responses that some
    proxies drop before the final chunk. Streaming reads keep every
    byte that arrived before a break, and Part VII sits early enough in
    the return that a long partial usually contains it whole. We keep
    the longest partial across attempts and accept it when it holds at
    least one complete Part VII group; a complete body is used as-is.
    """
    url = XML_URL.format(oid=object_id)
    headers = {"User-Agent": "ohack-grant-finder/2.0 (nonprofit research)"}
    best: bytes = b""
    for attempt in range(attempts):
        buf = bytearray()
        try:
            with session.get(url, headers=headers, timeout=45, stream=True) as resp:
                if resp.status_code != 200:
                    logger.debug("XML %s: HTTP %s", object_id, resp.status_code)
                    return None
                for chunk in resp.iter_content(chunk_size=16384):
                    if chunk:
                        buf.extend(chunk)
            data = bytes(buf)
            if b"Form990" in data[:4096]:
                return data
            return None
        except requests.RequestException as exc:
            logger.debug("XML %s attempt %d broke at %d bytes (%s)",
                         object_id, attempt, len(buf), type(exc).__name__)
            if len(buf) > len(best):
                best = bytes(buf)
            if b"</Form990PartVIISectionAGrp>" in best:
                return best
            time.sleep(1.0)
    if b"</Form990PartVIISectionAGrp>" in best:
        return best
    return None


def build_benchmarks(people: list[PersonComp]) -> list[dict]:
    """Median/quartile comp per role, overall and per revenue band.

    A bucket is only published with at least MIN_BUCKET_N people in it;
    thin slices stay out rather than dressing up two data points as a
    benchmark.
    """
    benchmarks: list[dict] = []

    def _add(role: str, band: str, values: list[float]) -> None:
        if len(values) < MIN_BUCKET_N:
            return
        values = sorted(values)
        benchmarks.append(
            {
                "role": role,
                "revenue_band": band,
                "count": len(values),
                "median": statistics.median(values),
                "p25": values[len(values) // 4],
                "p75": values[(3 * len(values)) // 4],
            }
        )

    for role in sorted({p.role for p in people}):
        _add(role, "All sizes", [p.comp_total for p in people if p.role == role])
        for band, _, _ in REVENUE_BANDS:
            _add(role, band, [p.comp_total for p in people
                              if p.role == role and _revenue_band(p.revenue) == band])
        _add(role, EXTRA_REVENUE_BAND_LABEL,
             [p.comp_total for p in people
              if p.role == role and p.revenue is not None
              and p.revenue < EXTRA_REVENUE_BAND_CEILING])
    return benchmarks



def _revenue_band(revenue: Optional[float]) -> str:
    if revenue is None:
        return "All sizes"
    for label, lo, hi in REVENUE_BANDS:
        if lo <= revenue < hi:
            return label
    return "All sizes"


def collect_comparable_eins(session: requests.Session, cap: int = 400) -> list[str]:
    """Arizona nonprofits across sectors, from ProPublica search."""
    queries = ["health", "hospital", "education", "school", "community", "services",
               "arts", "museum", "housing", "food", "youth", "foundation", "council"]
    eins: list[str] = []
    seen: set[str] = set()
    for q in queries:
        for page in range(2):
            try:
                resp = session.get(SEARCH_URL, params={"q": q, "state[id]": "AZ", "page": page}, timeout=30)
                resp.raise_for_status()
                orgs = resp.json().get("organizations") or []
            except (requests.RequestException, ValueError) as exc:
                logger.warning("salary org search failed (%s p%d): %s", q, page, exc)
                break
            for org in orgs:
                ein = str(org.get("ein") or "")
                if ein and ein not in seen:
                    seen.add(ein)
                    eins.append(ein)
            if not orgs:
                break
        if len(eins) >= cap:
            break
    logger.info("salary comparable candidates: %d EINs", len(eins))
    return eins[:cap]


def pick_samples(people: list[PersonComp], total: int = 60, small_slots: int = 30,
                 tiny_slots: int = 12) -> list[PersonComp]:
    """Highest-paid people nationally, plus reserved representation for
    small orgs. A straight top-N by pay contains no small orgs at all,
    so the explorer would show none. Slots are reserved in this order:

    1. tiny_slots: the highest-paid person at each of the best-paying
       very small orgs (revenue under $350K);
    2. small_slots: the highest-paid person at each of the best-paying
       small orgs (revenue under $1M) - a full small_slots of new picks
       on top of the tiny picks, so the tiny reservation does not eat
       into small-org representation;
    3. the remaining slots fill with the highest-paid people overall.
    """
    ranked = sorted(people, key=lambda p: p.comp_total, reverse=True)
    chosen: list[PersonComp] = []
    seen = set()

    def take(p: PersonComp) -> bool:
        key = (p.ein, p.title_raw, p.comp_total)
        if key not in seen:
            seen.add(key)
            chosen.append(p)
            return True
        return False

    def best_per_org(ceiling: float) -> list[PersonComp]:
        best: dict[str, PersonComp] = {}
        for p in people:
            if p.revenue is not None and p.revenue < ceiling:
                cur = best.get(p.ein)
                if cur is None or p.comp_total > cur.comp_total:
                    best[p.ein] = p
        return sorted(best.values(), key=lambda p: p.comp_total, reverse=True)

    tiny_taken = 0
    for p in best_per_org(EXTRA_REVENUE_BAND_CEILING):
        if tiny_taken >= tiny_slots:
            break
        if take(p):
            tiny_taken += 1
    small_taken = 0
    for p in best_per_org(1_000_000):
        if small_taken >= small_slots:
            break
        if take(p):
            small_taken += 1
    for p in ranked:
        if len(chosen) >= total:
            break
        take(p)
    return sorted(chosen, key=lambda p: p.comp_total, reverse=True)


def collect(max_orgs: int = 40, today: Optional[date] = None) -> dict:
    """Build salary benchmarks. Returns a JSON-ready dict (see pipeline)."""
    today = today or date.today()
    session = requests.Session()
    people: list[PersonComp] = []

    # Phase 1: find eligible organizations (Form 990, paid officers,
    # revenue in a comparable band, filing XML available). Mega health
    # systems are excluded by the revenue ceiling: their filings are
    # multi-megabyte and their pay scales are not the comparison a
    # typical nonprofit needs.
    eligible: list[dict] = []
    scanned = 0
    for ein in collect_comparable_eins(session):
        if len(eligible) >= max_orgs * 2 or scanned >= 220:
            break
        scanned += 1
        try:
            resp = session.get(ORG_URL.format(ein=ein), timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            continue
        org = data.get("organization") or {}
        filings = data.get("filings_with_data") or []
        if not filings:
            continue
        # The XML object id is NOT the number in the PDF filename (that
        # is a different 16-digit submission stamp that 404s). The org
        # record carries latest_object_id (18 digits) for its newest
        # filing; pair it with the filings_with_data row for the same
        # tax period so comp/revenue describe the same return.
        oid = str(org.get("latest_object_id") or "")
        period = str(org.get("tax_period") or "")[:7].replace("-", "")
        if len(oid) != 18 or len(period) != 6:
            continue
        filing = next((f for f in filings if str(f.get("tax_prd") or "") == period), None)
        if filing is not None:
            if "990PF" in (filing.get("pdf_url") or ""):
                continue  # 990-PF officer comp lives in a different part
            if not (filing.get("compnsatncurrofcr") or 0) > 0:
                continue  # no paid officers on this return
            revenue = filing.get("totrevenue")
        else:
            # The SOI extract lags the newest filing: no summary row for
            # this period yet. Fall back to the org record's revenue and
            # let the person-level filters in phase 2 do the gating.
            filing = {"tax_prd_yr": int(period[:4])}
            revenue = org.get("revenue_amount")
        if revenue is None or not (250_000 <= revenue <= 50_000_000):
            continue
        eligible.append({"org": org, "filing": filing, "oid": oid, "revenue": revenue})
    logger.info("salary: scanned %d candidates, %d eligible orgs", scanned, len(eligible))

    # Phase 2: fetch Part VII, smallest organizations first (smaller
    # filings transfer more reliably and are the most-used comparisons).
    eligible.sort(key=lambda e: e["revenue"])
    orgs_used = 0
    for entry in eligible:
        if orgs_used >= max_orgs:
            break
        org, filing = entry["org"], entry["filing"]
        xml = fetch_xml(entry["oid"], session)
        if xml is None:
            logger.info("salary: no usable XML for %s", org.get("name"))
            continue
        rows = parse_part_vii(xml)
        kept = 0
        for row in rows:
            if row["comp_total"] < MIN_COMP:
                continue
            if row["hours"] is not None and row["hours"] < MIN_HOURS:
                continue
            people.append(
                PersonComp(
                    org_name=org.get("name") or "",
                    ein=str(org.get("ein") or ""),
                    city=org.get("city") or "",
                    state=org.get("state") or "",
                    revenue=entry["revenue"],
                    filing_year=filing.get("tax_prd_yr"),
                    title_raw=row["title"][:80],
                    role=classify_role(row["title"]),
                    hours=row["hours"],
                    comp_total=row["comp_total"],
                )
            )
            kept += 1
        if kept:
            orgs_used += 1
        logger.info("salary: %s -> %d paid FT officers (orgs used: %d)",
                    org.get("name"), kept, orgs_used)

    benchmarks = build_benchmarks(people)
    samples = pick_samples(people)
    return {
        "benchmarks": benchmarks,
        "samples": [
            {
                "org_name": p.org_name, "ein": p.ein, "city": p.city, "state": p.state,
                "revenue": p.revenue, "filing_year": p.filing_year,
                "title": p.title_raw, "role": p.role, "hours": p.hours,
                "comp_total": p.comp_total,
            }
            for p in samples
        ],
        "methodology": {
            "source": "IRS Form 990 Part VII via ProPublica Nonprofit Explorer",
            "universe": "Arizona nonprofits filing Form 990 with paid officers; latest filing per organization",
            "filters": f"Only people with >= {MIN_HOURS:.0f} avg hours/week and >= ${MIN_COMP:,} total compensation (reportable from org + related orgs + other comp)",
            "organizations_used": orgs_used,
            "people_counted": len(people),
            "generated_at": today.isoformat(),
        },
    }
