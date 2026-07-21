from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.enrichment.public_data.client import PublicDataApiClient
from realty_radar.infrastructure.database.models import ApartmentComplex


class PublicDataSyncService:
    """공공 데이터 아파트 단지 정보 및 최근 실거래가 수집 동기화 서비스."""

    def __init__(self, db: Session):
        self.db = db
        self.client = PublicDataApiClient()

    async def sync_complex_public_data(self, complex_id: int) -> dict:
        """아파트 단지의 공공 데이터 정보 동기화."""
        stmt = select(ApartmentComplex).where(ApartmentComplex.id == complex_id)
        complex_item = self.db.scalar(stmt)

        if not complex_item:
            return {"status": "failed", "reason": "단지를 찾을 수 없습니다."}

        # MOCK/실거래 수집
        trades = await self.client.fetch_apartment_trades("11560", "202607")

        if trades and not complex_item.construction_year:
            complex_item.construction_year = trades[0].get("build_year", 1971)
            self.db.commit()

        return {
            "status": "success",
            "complex_id": complex_id,
            "fetched_trades_count": len(trades),
        }
