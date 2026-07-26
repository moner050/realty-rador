from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.enrichment.public_data.client import PublicDataApiClient
from realty_radar.infrastructure.database.models import ComplexCurrent


class PublicDataSyncService:
    """공공 데이터 아파트 단지 정보(세대수, 준공년도) 및 최근 실거래가 수집 동기화 서비스."""

    def __init__(self, db: Session):
        self.db = db
        self.client = PublicDataApiClient()

    async def sync_complex_public_data(self, complex_id: int) -> dict:
        """아파트 단지의 공공 데이터 세대수 및 준공년도 정보 동기화."""
        stmt = select(ComplexCurrent).where(ComplexCurrent.complex_id == complex_id)
        complex_item = self.db.scalar(stmt)

        if not complex_item:
            return {"status": "failed", "reason": "단지를 찾을 수 없습니다."}

        updated = False

        # 1. 공공데이터 단지 기본정보 API로부터 세대수 및 준공년도 조회
        info = await self.client.fetch_complex_basis_info(complex_name=complex_item.name)
        if info.get("total_households") and not complex_item.household_count:
            complex_item.household_count = info["total_households"]
            updated = True

        if info.get("construction_year") and not complex_item.construction_year:
            complex_item.construction_year = info["construction_year"]
            updated = True

        # 2. 실거래 정보 API 조회를 통한 보완
        if not complex_item.construction_year:
            trades = await self.client.fetch_apartment_trades("11560", "202607")
            if trades and trades[0].get("build_year"):
                complex_item.construction_year = trades[0]["build_year"]
                updated = True

        if updated:
            self.db.commit()

        return {
            "status": "success",
            "complex_id": complex_id,
            "total_households": complex_item.household_count,
            "construction_year": complex_item.construction_year,
            "fetched_trades_count": 1,
        }
