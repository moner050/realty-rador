"""Run a bounded SITE_A listing-detail enrichment with an explicit crawl job."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys


source_root = Path(__file__).resolve().parents[1] / "src"
if str(source_root) not in sys.path:
    sys.path.insert(0, str(source_root))

from realty_radar.application.mortgage_enrichment_service import run_site_a_mortgage_enrichment
from realty_radar.infrastructure.database.session import SessionFactory


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bounded SITE_A listing-detail enrichment.")
    parser.add_argument("--job-id", required=True, type=int)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-batches", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()

    if args.job_id <= 0:
        parser.error("--job-id must be positive")
    if not 1 <= args.batch_size <= 500:
        parser.error("--batch-size must be between 1 and 500")
    if args.max_batches <= 0:
        parser.error("--max-batches must be positive")
    if args.concurrency <= 0:
        parser.error("--concurrency must be positive")

    checked = asyncio.run(
        run_site_a_mortgage_enrichment(
            SessionFactory,
            job_id=args.job_id,
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            concurrency=args.concurrency,
        )
    )
    print(f"checked={checked}")


if __name__ == "__main__":
    main()
