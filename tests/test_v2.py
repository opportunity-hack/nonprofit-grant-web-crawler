"""Tests for Grant Finder v2 validation and source mapping.

Fixtures are trimmed copies of real API responses captured 2026-10-16.
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.v2.models import FundingAmount, GrantRecord
from src.v2.sources.grantsgov import hit_to_record
from src.v2.validate import parse_date, validate_grants

BUILD = date(2026, 10, 16)
FIXTURES = Path(__file__).parent / "fixtures"


def _record(**kw):
    base = dict(
        title="Example Grant",
        description="A real opportunity.",
        source_url="https://www.grants.gov/search-results-detail/1",
        source_name="Grants.gov",
        application_url="https://www.grants.gov/search-results-detail/1",
        source_api="grants.gov",
        source_id="grantsgov-1",
    )
    base.update(kw)
    return GrantRecord(**base)


def test_parse_date_formats():
    assert parse_date("2027-03-05") == date(2027, 3, 5)
    assert parse_date("03/05/2027") == date(2027, 3, 5)
    assert parse_date("March 5, 2027") == date(2027, 3, 5)
    assert parse_date("not a date") is None
    assert parse_date(None) is None


def test_past_deadline_is_dropped():
    kept, notes = validate_grants([_record(deadline_iso="2025-01-01")], BUILD)
    assert kept == []
    assert any("past" in n for n in notes)


def test_future_deadline_kept_and_formatted():
    kept, _ = validate_grants([_record(deadline_iso="2027-03-05")], BUILD)
    assert len(kept) == 1
    assert kept[0].deadline_iso == "2027-03-05"
    assert kept[0].deadline == "March 5, 2027"


def test_implausible_amount_nulled_not_dropped():
    # The legacy bug: "$110 million" scraped as 110, and small amounts
    # dropped the whole grant. Here the record survives, amount nulled.
    kept, notes = validate_grants(
        [_record(funding_amount=FundingAmount(amount=110))], BUILD
    )
    assert len(kept) == 1
    assert kept[0].funding_amount is None
    assert any("amount nulled" in n for n in notes)


def test_entities_decoded_and_deduped():
    rec = _record(title="Science &ndash; Technology &amp; Society")
    kept, _ = validate_grants([rec, _record()], BUILD)
    assert len(kept) == 1
    assert kept[0].title == "Science – Technology & Society"


def test_grantsgov_hit_mapping_uses_structured_fields():
    hits = json.loads((FIXTURES / "grantsgov_search.json").read_text())
    rec = hit_to_record(hits[0], "technology", "11", BUILD)
    assert rec is not None
    assert rec.source_api == "grants.gov"
    assert rec.application_url.endswith(str(hits[0]["id"]))
    assert rec.deadline_iso >= BUILD.isoformat()
    assert "501(c)(3)" in (rec.eligibility or "")


def test_title_gate_rejects_body_only_keyword_matches():
    from src.v2.sources.grantsgov import title_matches_keyword

    assert not title_matches_keyword("Genomic Variation Data Coordination Center", "technology")
    assert title_matches_keyword("Rural Broadband Expansion Program", "broadband")
    assert title_matches_keyword("AI Tools for Community Health Workers", "artificial intelligence")


def test_placeholder_2099_deadline_becomes_none():
    hits = json.loads((FIXTURES / "grantsgov_search.json").read_text())
    hit = dict(hits[0], closeDate="01/01/2099")
    rec = hit_to_record(hit, "technology", "11", BUILD)
    assert rec.deadline_iso is None and rec.deadline is None


# --- Salary benchmarking (Form 990 Part VII) ---

FIXTURE_990 = b"""<Return xmlns="http://www.irs.gov/efile"><ReturnData><IRS990>
<Form990PartVIISectionAGrp><PersonNm>A</PersonNm><TitleTxt>EXECUTIVE DIRECTOR</TitleTxt><AverageHrsPerWkRt>40</AverageHrsPerWkRt><ReportableCompFromOrgAmt>120000</ReportableCompFromOrgAmt><ReportableCompFromRltdOrgAmt>0</ReportableCompFromRltdOrgAmt><OtherCompensationAmt>8000</OtherCompensationAmt></Form990PartVIISectionAGrp>
<Form990PartVIISectionAGrp><PersonNm>B</PersonNm><TitleTxt>DIRECTOR</TitleTxt><AverageHrsPerWkRt>1</AverageHrsPerWkRt><ReportableCompFromOrgAmt>0</ReportableCompFromOrgAmt></Form990PartVIISectionAGrp>
</IRS990></ReturnData></Return>"""


def test_parse_part_vii_sums_all_comp_columns():
    from src.v2.sources.salaries import parse_part_vii

    rows = parse_part_vii(FIXTURE_990)
    assert len(rows) == 2
    assert rows[0]["comp_total"] == 128000  # org + related + other
    assert rows[0]["hours"] == 40.0


def test_classify_role_buckets():
    from src.v2.sources.salaries import classify_role

    assert classify_role("PRESIDENT/CEO") == "Executive Director / CEO"
    assert classify_role("CHIEF FINANCIAL OFFICER") == "Finance (CFO / Controller)"
    assert classify_role("DIRECTOR OF DEVELOPMENT") == "Development / Fundraising"
    assert classify_role("VP OF PROGRAMS") == "Programs"


def test_build_benchmarks_requires_minimum_sample():
    from src.v2.sources.salaries import PersonComp, build_benchmarks

    def person(comp, revenue=5_000_000):
        return PersonComp(org_name="Org", ein="1", city="Phoenix", revenue=revenue,
                          filing_year=2024, title_raw="CEO", role="Executive Director / CEO",
                          hours=40.0, comp_total=comp)

    thin = build_benchmarks([person(100_000), person(110_000)])
    assert thin == []  # 2 people is not a benchmark
    full = build_benchmarks([person(c) for c in (100_000, 120_000, 140_000, 160_000, 180_000)])
    all_sizes = [b for b in full if b["revenue_band"] == "All sizes"]
    assert len(all_sizes) == 1 and all_sizes[0]["median"] == 140_000 and all_sizes[0]["count"] == 5


def test_build_benchmarks_under_350k_is_an_extra_cut():
    from src.v2.sources.salaries import PersonComp, build_benchmarks

    def person(comp, revenue):
        return PersonComp(org_name="Org", ein="1", city="Phoenix", revenue=revenue,
                          filing_year=2024, title_raw="CEO", role="Executive Director / CEO",
                          hours=40.0, comp_total=comp)

    people = [person(c, 300_000) for c in (50_000, 60_000, 70_000, 80_000, 90_000)]
    people.append(person(100_000, 500_000))  # under $1M, but not under $350K
    rows = {(b["revenue_band"]): b for b in build_benchmarks(people)}
    # The $300K people count in all three bands; the $500K person only
    # in "Under $1M" and "All sizes".
    assert rows["Under $350K"]["count"] == 5 and rows["Under $350K"]["median"] == 70_000
    assert rows["Under $1M"]["count"] == 6
    assert rows["All sizes"]["count"] == 6


def test_build_benchmarks_under_350k_suppressed_below_minimum():
    from src.v2.sources.salaries import PersonComp, build_benchmarks

    def person(comp, revenue=300_000):
        return PersonComp(org_name="Org", ein="1", city="Phoenix", revenue=revenue,
                          filing_year=2024, title_raw="CEO", role="Executive Director / CEO",
                          hours=40.0, comp_total=comp)

    rows = build_benchmarks([person(c) for c in (50_000, 60_000, 70_000)])
    assert rows == []  # n=3 is below MIN_BUCKET_N in every band, new one included


def test_pick_samples_includes_under_350k_orgs():
    from src.v2.sources.salaries import PersonComp, pick_samples

    def person(ein, comp, revenue):
        return PersonComp(org_name=f"Org {ein}", ein=ein, city="Phoenix", revenue=revenue,
                          filing_year=2024, title_raw="CEO", role="Executive Director / CEO",
                          hours=40.0, comp_total=comp)

    people = [person(f"tiny-{i}", 50_000 + i * 1_000, 300_000) for i in range(5)]
    people += [person(f"small-{i}", 100_000 + i * 1_000, 900_000) for i in range(30)]
    people += [person(f"large-{i}", 500_000 + i * 1_000, 20_000_000) for i in range(60)]
    samples = pick_samples(people)
    assert len(samples) == 60
    sampled_eins = {p.ein for p in samples}
    # The tiny orgs pay the least, so only the reserved slots get them in.
    assert all(f"tiny-{i}" in sampled_eins for i in range(5))
    assert sum(1 for p in samples if p.revenue < 1_000_000) >= 35


def test_parse_part_vii_tolerates_truncated_xml():
    from src.v2.sources.salaries import parse_part_vii

    cut = FIXTURE_990.find(b"</Form990PartVIISectionAGrp>") + 60
    truncated = FIXTURE_990[:cut]  # first group complete, rest cut off
    rows = parse_part_vii(truncated)
    # The first (complete) group survives; the cut group does not.
    assert len(rows) == 1 and rows[0]["comp_total"] == 128000
