"""Grant Finder v2 pipeline.

Usage:
    python -m src.v2.pipeline [--output-dir data/output] [--no-details]

Fetches from all structured sources, validates, and writes the two
files the /nonprofit-grants page consumes:

    opportunity_hack_grants.json  - array of grant records (page cards)
    report_data.json              - summary stats, sector/tech counts,
                                    and the Arizona funders (990) list

Every run logs per-source fetched/kept/dropped counts. Nothing is
written unless validation produced at least one record.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from .models import FunderRecord, GrantRecord
from .sources import curated, grantsgov, propublica
from .validate import validate_grants

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("grant_finder_v2.pipeline")


def build_report(grants: list[GrantRecord], funders: list[FunderRecord], build_date: date) -> dict:
    amounts = [g.funding_amount.amount for g in grants if g.funding_amount]
    sectors = Counter(s for g in grants for s in g.nonprofit_sector)
    tech = Counter(t for g in grants for t in g.tech_focus)
    return {
        "summary": {
            "total_grants": len(grants),
            "grants_with_deadlines": sum(1 for g in grants if g.deadline_iso),
            "grants_with_amounts": len(amounts),
            # A median across a handful of amounts would mislead; only
            # publish it once at least 10 records carry structured amounts.
            "median_award": statistics.median(amounts) if len(amounts) >= 10 else None,
            "funders_count": len(funders),
            "timestamp": build_date.isoformat(),
        },
        "nonprofit_sectors": dict(sectors.most_common()),
        "tech_focus": dict(tech.most_common()),
        "funders": [f.model_dump() for f in funders],
    }


def run(output_dir: Path, fetch_amounts: bool = True) -> tuple[Path, Path]:
    build_date = date.today()
    logger.info("Grant Finder v2 run started (build date %s)", build_date)

    federal = grantsgov.collect(fetch_amounts=fetch_amounts, today=build_date)
    logger.info("source grants.gov: %d records before validation", len(federal))
    programs = curated.collect(today=build_date)
    logger.info("source curated: %d records", len(programs))
    funders = propublica.collect(today=build_date)
    logger.info("source propublica: %d funders", len(funders))

    kept, notes = validate_grants(federal + programs, build_date)
    for note in notes:
        logger.info("validation: %s", note)
    logger.info("validation kept %d of %d records", len(kept), len(federal) + len(programs))
    if not kept:
        raise SystemExit("Validation produced zero records; refusing to overwrite data.")

    output_dir.mkdir(parents=True, exist_ok=True)
    grants_path = output_dir / "opportunity_hack_grants.json"
    report_path = output_dir / "report_data.json"
    grants_path.write_text(
        json.dumps([g.model_dump() for g in kept], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(build_report(kept, funders, build_date), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("wrote %s (%d grants) and %s", grants_path, len(kept), report_path)
    return grants_path, report_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grant Finder v2 pipeline")
    parser.add_argument("--output-dir", type=Path, default=Path("data/output"))
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Skip Grants.gov award-amount enrichment (faster, amounts stay empty)",
    )
    args = parser.parse_args(argv)
    run(args.output_dir, fetch_amounts=not args.no_details)
    return 0


if __name__ == "__main__":
    sys.exit(main())
