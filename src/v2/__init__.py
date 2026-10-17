"""Grant Finder v2: structured-source grant discovery.

V2 replaces regex web scraping (the legacy crawler in src/utils) with
official structured APIs whose fields can be trusted:

- Grants.gov API for open federal opportunities (agency, close date,
  eligibility, assistance listings, award ceilings when available).
- ProPublica Nonprofit Explorer API (IRS Form 990 data) for Arizona
  grantmaking foundations.
- A small hand-verified list of recurring tech-for-nonprofit programs.

Every record carries its source and retrieval date, deadlines are real
parsed dates that must be in the future at build time, and dollar amounts
only ever come from structured fields, never from page text.
"""
