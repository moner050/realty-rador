from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.crawler.base.models import NormalizedListing
from realty_radar.infrastructure.database.models import CrawlSource, Listing, ListingHistory


class ListingUpsertService:
    """수집된 NormalizedListing 객체를 마스터 DB에 생성 또는 업데이트(Upsert)하는 서비스."""

    def __init__(self, db: Session):
        self.db = db

    def _get_or_create_source_id(self, source_code: str) -> int:
        """출처 사이트 코드로 source_id 조회 및 없으면 새로 생성."""
        stmt = select(CrawlSource).where(CrawlSource.source_code == source_code)
        source = self.db.scalar(stmt)
        if not source:
            source = CrawlSource(
                source_code=source_code,
                source_name=f"부동산 사이트 ({source_code})",
                base_url=f"https://{source_code.lower()}.com",
            )
            self.db.add(source)
            self.db.flush()
        return source.id

    def upsert_listing(self, item: NormalizedListing) -> tuple[Listing, bool]:
        """매물 단건 Upsert 수행 및 생성/수정 여부 반환."""
        source_id = self._get_or_create_source_id(item.source_code)

        stmt = select(Listing).where(
            Listing.source_id == source_id,
            Listing.external_listing_id == item.external_listing_id,
        )
        existing_listing = self.db.scalar(stmt)

        now = datetime.now()
        is_created = False

        price_val = getattr(item, "sale_price", None) or getattr(item, "deposit", None) or getattr(item, "price_deposit", 0)
        monthly_val = getattr(item, "monthly_rent", None) or getattr(item, "price_monthly", 0)
        status_val = getattr(item, "listing_status", None) or getattr(item, "status", None)
        status_str = status_val.value if hasattr(status_val, "value") else str(status_val or "ACTIVE")
        mortgage_val = getattr(item, "mortgage_status", None)
        mortgage_str = mortgage_val.value if hasattr(mortgage_val, "value") else str(mortgage_val or "UNKNOWN")
        tx_val = getattr(item, "transaction_type", None)
        tx_str = tx_val.value if hasattr(tx_val, "value") else str(tx_val or "SALE")

        # 층수 표시 정보 결정 (1순위: 숫자/전체 층 조합, 2순위: 원본 floor_raw 텍스트(예: "중/15층"), 3순위: fallback)
        fl_num = getattr(item, "floor_number", None)
        tot_fl = getattr(item, "total_floor", None) or getattr(item, "total_floors", None)
        fl_grp = getattr(item, "floor_group", None)
        fl_raw = getattr(item, "floor_raw", None) or getattr(item, "floor_info", None)

        if fl_num and tot_fl:
            floor_str = f"{fl_num}/{tot_fl}층"
        elif fl_num:
            floor_str = f"{fl_num}층"
        elif fl_raw and fl_raw.strip():
            floor_str = fl_raw.strip()
        elif fl_grp and tot_fl:
            floor_str = f"{fl_grp}/{tot_fl}층"
        else:
            floor_str = fl_grp or "-"

        desc_str = getattr(item, "description", None) or getattr(item, "description_raw", None)

        if not existing_listing:
            existing_listing = Listing(
                source_id=source_id,
                external_listing_id=item.external_listing_id,
                source_url=item.source_url,
                complex_name_raw=item.complex_name_raw,
                address_raw=item.address_raw,
                transaction_type=tx_str,
                price_deposit=price_val,
                price_monthly=monthly_val,
                supply_area=item.supply_area,
                exclusive_area=item.exclusive_area,
                floor_info=floor_str,
                mortgage_status=mortgage_str,
                description_raw=desc_str,
                status=status_str,
                first_seen_at=now,
                last_seen_at=now,
                stale_count=0,
            )
            self.db.add(existing_listing)
            self.db.flush()
            is_created = True

            # 이력 기록
            history = ListingHistory(
                listing_id=existing_listing.id,
                change_type="CREATED",
                new_price_deposit=price_val,
                new_status=status_str,
                note="최초 매물 수집 등록",
            )
            self.db.add(history)

        else:
            # 기존 매물 업데이트 및 가격 변동 이력 기록
            if existing_listing.price_deposit != price_val:
                history = ListingHistory(
                    listing_id=existing_listing.id,
                    change_type="PRICE_CHANGE",
                    prev_price_deposit=existing_listing.price_deposit,
                    new_price_deposit=price_val,
                    note="가격 변동 감지",
                )
                self.db.add(history)
                existing_listing.price_deposit = price_val

            existing_listing.last_seen_at = now
            existing_listing.stale_count = 0
            existing_listing.status = status_str
            existing_listing.floor_info = floor_str

        self.db.commit()
        return existing_listing, is_created
