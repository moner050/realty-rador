from datetime import datetime
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from realty_radar.infrastructure.database.models.base import Base


class Listing(Base):
    """통합 매물 실시간 수집 마스터 테이블 (100% 한글 코멘트 및 초고속 인덱스 탑재)."""

    __tablename__ = "listing"
    __table_args__ = (
        Index("idx_listing_source_ext", "source_id", "external_listing_id"),
        Index("idx_listing_dedup_lookup", "complex_id", "transaction_type", "exclusive_area"),
        Index("idx_listing_search_sale", "transaction_type", "price_deposit", "exclusive_area"),
        Index("idx_listing_search_rent", "transaction_type", "price_monthly", "exclusive_area"),
        Index("idx_listing_complex_status", "complex_id", "status"),
        Index("idx_listing_status_seen", "status", "last_seen_at"),
        Index("idx_listing_mortgage", "mortgage_status"),
        {"comment": "통합 부동산 매물 마스터 테이블"},
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, comment="매물 고유 일련번호 (PK)")
    source_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("crawl_source.id"), nullable=False, comment="수집 출처 사이트 식별자 (FK)")
    complex_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("apartment_complex.id", ondelete="SET NULL"), nullable=True, comment="매칭된 아파트 단지 식별자 (FK)")

    external_listing_id = Column(String(100), nullable=False, comment="출처 사이트 원본 매물 고유 번호")
    canonical_group_id = Column(String(100), nullable=True, comment="다중 사이트 동일 매물 추정 대표 그룹 ID")

    source_url = Column(Text, nullable=False, comment="원본 매물 상세 접속 URL")
    complex_name_raw = Column(String(100), nullable=False, comment="수집된 원본 아파트 단지명")
    address_raw = Column(String(200), nullable=True, comment="수집된 원본 매물 상세 주소")

    transaction_type = Column(String(20), nullable=False, comment="거래 유형 (SALE: 매매, JEONSE: 전세, MONTHLY_RENT: 월세)")
    price_deposit = Column(Numeric(15, 2), nullable=False, comment="매매가 또는 전/월세 보증금 (단위: 원)")
    price_monthly = Column(Numeric(15, 2), default=0, nullable=False, comment="월세액 (단위: 원, 매매/전세 시 0)")

    supply_area = Column(Numeric(8, 2), nullable=True, comment="공급면적 (단위: ㎡)")
    exclusive_area = Column(Numeric(8, 2), nullable=True, comment="전용면적 (단위: ㎡)")
    floor_info = Column(String(50), nullable=True, comment="층수 정보 (예: 고/15층, 7/12층)")

    mortgage_status = Column(String(30), default="UNKNOWN", nullable=False, comment="융자 상태 (EXPLICIT_NONE: 없음, EXPLICIT_EXISTS: 있음, UNKNOWN: 미확인)")
    description_raw = Column(Text, nullable=True, comment="수집된 원본 매물 상세 설명 문구")

    status = Column(String(30), default="ACTIVE", nullable=False, comment="매물 상태 (ACTIVE: 유효, STALE: 미확인, REMOVED: 삭제됨, SOLD_OR_CONTRACTED: 거래완료)")
    first_seen_at = Column(DateTime, default=datetime.now, nullable=False, comment="최초 크롤링 발견 일시")
    last_seen_at = Column(DateTime, default=datetime.now, nullable=False, comment="최근 크롤링 확인 일시")
    stale_count = Column(Integer, default=0, nullable=False, comment="연속 미발견 누적 횟수")

    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="매물 레코드 생성 일시")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="매물 레코드 수정 일시")

    # 관계 정의
    source = relationship("CrawlSource")
    complex = relationship("ApartmentComplex", back_populates="listings")
    histories = relationship("ListingHistory", back_populates="listing", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        if "sale_price" in kwargs:
            kwargs["price_deposit"] = kwargs.pop("sale_price")
        if "deposit" in kwargs:
            kwargs["price_deposit"] = kwargs.pop("deposit")
        if "monthly_rent" in kwargs:
            kwargs["price_monthly"] = kwargs.pop("monthly_rent")
        if "floor_group" in kwargs:
            kwargs["floor_info"] = kwargs.pop("floor_group")
        if "floor_number" in kwargs:
            fn = kwargs.pop("floor_number")
            tf = kwargs.pop("total_floors", kwargs.pop("total_floor", None))
            kwargs["floor_info"] = f"{fn}/{tf}층" if tf else f"{fn}층"
        elif "total_floors" in kwargs or "total_floor" in kwargs:
            kwargs.pop("total_floors", None)
            kwargs.pop("total_floor", None)
        if "description" in kwargs:
            kwargs["description_raw"] = kwargs.pop("description")
        if "raw_description" in kwargs:
            kwargs["description_raw"] = kwargs.pop("raw_description")
        if "raw_address" in kwargs:
            kwargs["address_raw"] = kwargs.pop("raw_address")
        if "mortgage_raw_text" in kwargs:
            kwargs.pop("mortgage_raw_text")
        if "raw_data" in kwargs:
            kwargs.pop("raw_data")
        if "raw_payload" in kwargs:
            kwargs.pop("raw_payload")
        if "listing_status" in kwargs:
            val = kwargs.pop("listing_status")
            kwargs["status"] = val.value if hasattr(val, "value") else str(val)
        super().__init__(**kwargs)

    @property
    def sale_price(self):
        return self.price_deposit

    @sale_price.setter
    def sale_price(self, val):
        self.price_deposit = val

    @property
    def deposit(self):
        return self.price_deposit

    @deposit.setter
    def deposit(self, val):
        self.price_deposit = val

    @property
    def monthly_rent(self):
        return self.price_monthly

    @monthly_rent.setter
    def monthly_rent(self, val):
        self.price_monthly = val

    @property
    def floor_group(self):
        return self.floor_info

    @floor_group.setter
    def floor_group(self, val):
        self.floor_info = val

    @property
    def description(self):
        return self.description_raw

    @description.setter
    def description(self, val):
        self.description_raw = val

    @property
    def listing_status(self):
        return self.status

    @listing_status.setter
    def listing_status(self, val):
        self.status = val.value if hasattr(val, "value") else str(val)


class ListingHistory(Base):
    """매물 변경 이력 및 동일 매물 추정 이력 테이블 (100% 한글 코멘트 적용)."""

    __tablename__ = "listing_history"
    __table_args__ = (
        Index("idx_history_listing_date", "listing_id", "created_at"),
        {"comment": "매물 가격 변동 및 상태 변경 이력 테이블"},
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, comment="이력 고유 일련번호 (PK)")
    listing_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("listing.id", ondelete="CASCADE"), nullable=False, comment="연결된 매물 식별자 (FK)")

    change_type = Column(String(50), nullable=False, comment="변경 유형 (PRICE_CHANGE: 가격변동, STATUS_CHANGE: 상태변경, CREATED: 최초생성)")
    prev_price_deposit = Column(Numeric(15, 2), nullable=True, comment="변경 전 보증금 또는 매매가 (단위: 원)")
    new_price_deposit = Column(Numeric(15, 2), nullable=True, comment="변경 후 보증금 또는 매매가 (단위: 원)")

    prev_status = Column(String(30), nullable=True, comment="변경 전 매물 상태")
    new_status = Column(String(30), nullable=True, comment="변경 후 매물 상태")

    note = Column(Text, nullable=True, comment="이력 발생 상세 설명 및 비고")
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="이력 기록 일시")

    # 관계 정의
    listing = relationship("Listing", back_populates="histories")

    @property
    def sale_price(self):
        return self.new_price_deposit

    @sale_price.setter
    def sale_price(self, val):
        self.new_price_deposit = val


# 기존 테스트 코드 하위 호환 별칭
ListingSnapshot = ListingHistory
