from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from realty_radar.infrastructure.database.models.base import Base


class ApartmentComplex(Base):
    """아파트 단지 마스터 정보 테이블 (100% 한글 코멘트 및 동 공간 인덱스 적용)."""

    __tablename__ = "apartment_complex"
    __table_args__ = (
        Index("idx_complex_name", "normalized_name"),
        Index("idx_complex_dong_norm", "dong", "normalized_name"),
        Index("idx_complex_region", "sido", "sigungu", "dong"),
        Index("idx_complex_build_household", "construction_year", "total_households"),
        {"comment": "아파트 단지 마스터 정보 테이블"},
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, comment="아파트 단지 고유 일련번호 (PK)")
    complex_code = Column(String(50), unique=True, nullable=True, comment="네이버/공공데이터 고유 단지 코드")
    official_name = Column(String(100), nullable=False, comment="아파트 공식 단지명 (예: 여의도 시범아파트)")
    normalized_name = Column(String(100), nullable=False, comment="검색 정규화 단지명 (특수문자/공백 제거)")

    sido = Column(String(50), nullable=True, comment="시/도 명칭 (예: 서울특별시, 경기도)")
    sigungu = Column(String(50), nullable=True, comment="시/군/구 명칭 (예: 영등포구, 분당구)")
    dong = Column(String(50), nullable=True, comment="법정동/행정동 명칭 (예: 여의도동, 백현동)")
    road_address = Column(String(200), nullable=True, comment="도로명 또는 지번 상세 주소")

    total_households = Column(Integer, nullable=True, comment="단지 총 세대수")
    total_buildings = Column(Integer, nullable=True, comment="단지 총 동수")
    construction_year = Column(Integer, nullable=True, comment="준공 연도 (YYYY, 예: 1971)")
    use_approval_date = Column(String(20), nullable=True, comment="사용승인 일자 (YYYY-MM-DD)")

    builder_name = Column(String(100), nullable=True, comment="건설사/시공사명")
    heat_type = Column(String(50), nullable=True, comment="난방 방식 (예: 지역난방, 개별난방)")

    latitude = Column(Numeric(10, 7), nullable=True, comment="위도 좌표 (Latitude)")
    longitude = Column(Numeric(10, 7), nullable=True, comment="경도 좌표 (Longitude)")

    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="단지 레코드 등록 일시")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="단지 레코드 수정 일시")

    # 관계 정의
    aliases = relationship("ComplexAlias", back_populates="complex", cascade="all, delete-orphan")
    listings = relationship("Listing", back_populates="complex")

    def __init__(self, **kwargs):
        if "sido_name" in kwargs:
            kwargs["sido"] = kwargs.pop("sido_name")
        if "sigungu_name" in kwargs:
            kwargs["sigungu"] = kwargs.pop("sigungu_name")
        if "legal_dong_name" in kwargs:
            kwargs["dong"] = kwargs.pop("legal_dong_name")
        if "household_count" in kwargs:
            kwargs["total_households"] = kwargs.pop("household_count")
        super().__init__(**kwargs)

    @property
    def sido_name(self):
        return self.sido

    @sido_name.setter
    def sido_name(self, val):
        self.sido = val

    @property
    def sigungu_name(self):
        return self.sigungu

    @sigungu_name.setter
    def sigungu_name(self, val):
        self.sigungu = val

    @property
    def legal_dong_name(self):
        return self.dong

    @legal_dong_name.setter
    def legal_dong_name(self, val):
        self.dong = val

    @property
    def household_count(self):
        return self.total_households

    @household_count.setter
    def household_count(self, val):
        self.total_households = val


class ComplexAlias(Base):
    """단지명 수집 매칭 및 별칭 관리 테이블 (100% 한글 코멘트 적용)."""

    __tablename__ = "complex_alias"
    __table_args__ = (
        Index("idx_alias_normalized", "normalized_alias"),
        Index("idx_alias_complex_norm", "complex_id", "normalized_alias"),
        {"comment": "단지명 매칭 및 별칭 매핑 테이블"},
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True, comment="단지 별칭 고유 일련번호 (PK)")
    complex_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("apartment_complex.id", ondelete="CASCADE"), nullable=False, comment="연결된 아파트 단지 식별자 (FK)")
    source_id = Column(BigInteger().with_variant(Integer, "sqlite"), ForeignKey("crawl_source.id"), nullable=True, comment="수집 출처 사이트 식별자 (FK)")

    alias_name = Column(String(100), nullable=False, comment="수집된 원본 매물 단지명")
    normalized_alias = Column(String(100), nullable=False, comment="정규화된 단지 별칭")

    match_method = Column(String(30), nullable=False, comment="매칭 연산 방식 (ADDRESS_EXACT: 주소일치, NAME_EXACT: 명칭일치, FUZZY: 유사도, MANUAL: 수동)")
    match_confidence = Column(Numeric(5, 2), nullable=True, comment="매칭 신뢰도 점수 (0.00 ~ 99.99)")
    manually_verified = Column(Boolean, default=False, nullable=False, comment="관리자 수동 검증 완료 여부")

    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="별칭 매핑 등록 일시")

    # 관계 정의
    complex = relationship("ApartmentComplex", back_populates="aliases")
