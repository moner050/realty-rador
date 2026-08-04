"""NAVER Maps로 누락 단지 좌표를 명시적으로 보강한다."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys


source_root = Path(__file__).resolve().parents[1] / "src"
if str(source_root) not in sys.path:
    sys.path.insert(0, str(source_root))

from realty_radar.enrichment.naver_maps.backfill import ComplexGeocodeBackfill
from realty_radar.enrichment.naver_maps.geocoder import NaverGeocoder
from realty_radar.infrastructure.database.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="누락된 단지 좌표를 NAVER Maps 지오코딩으로 보강합니다.")
    parser.add_argument("--batch-size", type=int, default=100, help="이번 실행에서 처리할 최대 단지 수 (기본값: 100)")
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

    session = SessionLocal()
    try:
        stats = ComplexGeocodeBackfill(session, NaverGeocoder()).run(
            batch_size=args.batch_size,
            now=datetime.now(timezone.utc).replace(tzinfo=None),
            complex_ids=args.complex_ids,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(
        f"selected={stats.selected_count} ok={stats.ok_count} "
        f"not_found={stats.not_found_count} failed={stats.failed_count}"
    )


if __name__ == "__main__":
    main()
