"""Validation for Grant Finder v2.

These rules exist because of specific legacy failures (see the Oct 2026
code review): amounts mangled by regex ("$110 million" became 110 USD),
deadlines stored as unparsed strings and never compared to today, and
records silently dropped when an amount looked small. The rules here:

- A deadline must parse into a real date; dated opportunities whose
  deadline is before the build date are dropped, with the drop logged.
- A bad amount never drops a record and is never "fixed up": it is
  nulled and logged. Amounts arrive only from structured API fields.
- Titles/descriptions are entity-decoded and whitespace-normalized.
- Records are deduped on their source id, then normalized URL.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import date, datetime
from typing import List, Tuple

from .models import GrantRecord

logger = logging.getLogger("grant_finder_v2.validate")

MIN_PLAUSIBLE_AWARD = 500
MAX_PLAUSIBLE_AWARD = 1_000_000_000

_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y")


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def clean_text(value: str | None, limit: int = 600) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


def validate_grants(
    records: List[GrantRecord], build_date: date
) -> Tuple[List[GrantRecord], List[str]]:
    """Return (kept records, human-readable drop/fix notes)."""
    kept: List[GrantRecord] = []
    notes: List[str] = []
    seen: set[str] = set()

    for rec in records:
        rec.title = clean_text(rec.title, limit=200)
        rec.description = clean_text(rec.description)

        if not rec.title or not rec.application_url:
            notes.append(f"dropped (missing title/url): {rec.title or rec.source_id}")
            continue

        # Deadline: must be a real date, and in the future when present.
        if rec.deadline_iso:
            parsed = parse_date(rec.deadline_iso)
            if parsed is None:
                notes.append(f"deadline nulled (unparseable): {rec.title}")
                rec.deadline = None
                rec.deadline_iso = None
            elif parsed < build_date:
                notes.append(f"dropped (deadline {parsed} past): {rec.title}")
                continue
            else:
                rec.deadline_iso = parsed.isoformat()
                rec.deadline = parsed.strftime("%B %-d, %Y")

        # Amount: structured fields only; implausible values are nulled,
        # never guessed at, and never cause the record to be dropped.
        if rec.funding_amount is not None:
            amt = rec.funding_amount.amount
            if amt < MIN_PLAUSIBLE_AWARD or amt > MAX_PLAUSIBLE_AWARD:
                notes.append(f"amount nulled ({amt}): {rec.title}")
                rec.funding_amount = None

        key = rec.source_id or rec.application_url.rstrip("/").lower()
        if key in seen:
            notes.append(f"dropped (duplicate): {rec.title}")
            continue
        seen.add(key)
        kept.append(rec)

    # Soonest deadline first; undated (rolling) opportunities last.
    kept.sort(key=lambda r: (r.deadline_iso is None, r.deadline_iso or "9999"))
    return kept, notes
