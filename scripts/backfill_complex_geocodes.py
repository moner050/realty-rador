"""NAVER Maps로 누락 단지 좌표를 명시적으로 보강한다."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys


source_root = Path(__file__).resolve().parents[1] / "src"
if str(source_root) not in sys.path:
    sys.path.insert(0, str(source_root))

from realty_radar.enrichment.naver_maps.backfill import run_geocode_sweep
from realty_radar.enrichment.naver_maps.geocoder import NaverGeocoder
from realty_radar.infrastructure.database.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="누락된 단지 좌표를 NAVER Maps 지오코딩으로 보강합니다.")
    parser.add_argument("--batch-size", type=int, default=100, help="이번 실행에서 처리할 최대 단지 수 (기본값: 100)")
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument("--max-requests", type=int, default=15000)
    parser.add_argument(
        "--complex-id",
        type=int,
        action="append",
        dest="complex_ids",
        help="지정한 단지만 처리합니다. 여러 번 지정할 수 있습니다.",
    )
    args = parser.parse_args()
    if args.batch_size <= 0:
        parser.error("--batch-size는 양수여야 합니다.")

    if args.max_batches <= 0:
        parser.error("--max-batches must be positive")
    if args.max_requests <= 0:
        parser.error("--max-requests must be positive")

    stats = run_geocode_sweep(
        SessionLocal,
        NaverGeocoder(),
        now=datetime.now(timezone.utc).replace(tzinfo=None),
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        max_requests=args.max_requests,
        complex_ids=args.complex_ids,
    )

    print(
        f"batch_count={stats.batch_count} selected_count={stats.selected_count} "
        f"external_request_count={stats.external_request_count} reused_count={stats.reused_count} "
        f"ok_count={stats.ok_count} not_found_count={stats.not_found_count} "
        f"failed_count={stats.failed_count}"
    )


if __name__ == "__main__":
    main()
