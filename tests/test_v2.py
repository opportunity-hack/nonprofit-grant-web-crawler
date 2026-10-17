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
