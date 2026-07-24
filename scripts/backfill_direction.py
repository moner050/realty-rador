# -*- coding: utf-8 -*-
"""기존 매물 데이터에서 description_raw의 방향 키워드를 추출하여 direction 칼럼에 백필하는 스크립트."""
import re
import logging
from realty_radar.infrastructure.database.session import SessionFactory
from realty_radar.infrastructure.database.models import Listing

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# 방향 키워드 정규식 (긴 것 우선 매칭)
DIRECTION_PATTERNS = [
    "남동향", "남서향", "북동향", "북서향",
    "남향", "동향", "서향", "북향",
]
DIRECTION_RE = re.compile("|".join(DIRECTION_PATTERNS))


def backfill_direction():
    """description_raw에서 방향 키워드를 추출하여 direction 칼럼 일괄 업데이트."""
    session = SessionFactory()
    try:
        # direction이 NULL인 매물만 대상
        listings = (
            session.query(Listing)
            .filter(Listing.direction == None, Listing.description_raw != None)
            .all()
        )
        logger.info(f"백필 대상 매물: {len(listings)}건")

        updated = 0
        batch_size = 1000
        for i, listing in enumerate(listings):
            desc = listing.description_raw or ""
            match = DIRECTION_RE.search(desc)
            if match:
                listing.direction = match.group(0)
                updated += 1

            # 1000건마다 커밋
            if (i + 1) % batch_size == 0:
                session.commit()
                logger.info(f"진행: {i + 1}/{len(listings)} (업데이트: {updated}건)")

        session.commit()
        logger.info(f"백필 완료! 총 {updated}/{len(listings)}건 방향 데이터 업데이트됨")
    finally:
        session.close()


if __name__ == "__main__":
    backfill_direction()
