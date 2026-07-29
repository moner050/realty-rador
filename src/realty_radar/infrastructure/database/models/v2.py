"""SITE_A 전용 MySQL 8.4 hot/cold 저장 모델.

운영 스키마는 Alembic ``001_site_a_v2`` migration이 권위 원본이다. 이
모듈은 애플리케이션의 타입 안전한 SQL 조립과 SQLite 단위 테스트를 위해 같은
열 계약을 표현한다. 외부 ID는 모두 SITE_A가 제공하는 숫자 ID를 그대로 쓴다.
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Computed,
    Date,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import relationship

from realty_radar.infrastructure.database.models.base import Base


UnsignedBigInt = mysql.BIGINT(unsigned=True).with_variant(Integer, "sqlite")
UnsignedInteger = mysql.INTEGER(unsigned=True).with_variant(Integer, "sqlite")
UnsignedMediumInt = mysql.MEDIUMINT(unsigned=True).with_variant(Integer, "sqlite")
UnsignedSmallInt = mysql.SMALLINT(unsigned=True).with_variant(Integer, "sqlite")
UnsignedTinyInt = mysql.TINYINT(unsigned=True).with_variant(Integer, "sqlite")
DateTime6 = mysql.DATETIME(fsp=6).with_variant(mysql.DATETIME(), "sqlite")
Hash16 = mysql.BINARY(16).with_variant(LargeBinary(16), "sqlite")


class ComplexCurrent(Base):
    """단지 탐색·보강에만 쓰는 작은 SITE_A 단지 현재 상태 테이블."""

    __tablename__ = "complex_current"
    __table_args__ = (
        Index("ix_complex_region_name", "sigungu_code", "normalized_name", "complex_id"),
        Index("ix_complex_build", "sigungu_code", "construction_year", "household_count", "complex_id"),
        Index(
            "ft_complex_name",
            "name",
            "normalized_name",
            "address",
            mysql_prefix="FULLTEXT",
            mysql_with_parser="ngram",
        ),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    complex_id = Column(UnsignedBigInt, primary_key=True, autoincrement=False)
    region_code = Column(UnsignedBigInt, nullable=False)
    # CAST 기반 식은 SQLite 테스트와 MySQL 모두에서 동작한다. 운영 migration은
    # 동등한 DIV 식으로 생성해 MySQL의 정수 나눗셈을 명시한다.
    sido_code = Column(
        UnsignedSmallInt,
        Computed("CAST(region_code / 100000000 AS UNSIGNED)", persisted=True),
        nullable=False,
    )
    sigungu_code = Column(
        UnsignedInteger,
        Computed("CAST(region_code / 100000 AS UNSIGNED)", persisted=True),
        nullable=False,
    )
    name = Column(String(120), nullable=False)
    normalized_name = Column(String(120), nullable=False)
    address = Column(String(240), nullable=False)
    construction_year = Column(UnsignedSmallInt, nullable=False, server_default=text("0"))
    household_count = Column(UnsignedMediumInt, nullable=False, server_default=text("0"))
    state_hash = Column(Hash16, nullable=False)
    first_seen_at = Column(DateTime6, nullable=False)
    last_seen_at = Column(DateTime6, nullable=False)
    updated_at = Column(DateTime6, nullable=False)

    listings = relationship("ListingCurrent", back_populates="complex")


class ListingCurrent(Base):
    """검색 화면이 JOIN 없이 읽는 SITE_A 매물 hot table."""

    __tablename__ = "listing_current"
    __table_args__ = (
        Index("ix_listing_price_all", "lifecycle", "is_short_term", "primary_price", "article_id"),
        Index("ix_listing_price_tx", "lifecycle", "is_short_term", "trade_type", "primary_price", "article_id"),
        Index("ix_listing_price_sido", "lifecycle", "is_short_term", "sido_code", "primary_price", "article_id"),
        Index("ix_listing_price_sigungu", "lifecycle", "is_short_term", "sigungu_code", "primary_price", "article_id"),
        Index(
            "ix_listing_price_sigungu_tx",
            "lifecycle",
            "is_short_term",
            "sigungu_code",
            "trade_type",
            "primary_price",
            "article_id",
        ),
        Index("ix_listing_recent", "lifecycle", "is_short_term", "first_seen_at", "article_id"),
        Index("ix_listing_area", "lifecycle", "is_short_term", "exclusive_area_x100", "article_id"),
        Index("ix_listing_households", "lifecycle", "is_short_term", "household_count", "article_id"),
        Index("ix_listing_construction_year", "lifecycle", "is_short_term", "construction_year", "article_id"),
        Index("ix_listing_complex", "complex_id", "lifecycle", "is_short_term", "primary_price", "article_id"),
        Index(
            "ix_listing_group_cover",
            "lifecycle",
            "is_short_term",
            "complex_id",
            "primary_price",
            "article_id",
            "first_seen_at",
            "exclusive_area_x100",
            "household_count",
            "region_code",
            "sido_code",
            "sigungu_code",
            "trade_type",
            "construction_year",
            "monthly_rent",
        ),
        Index("ix_listing_presence", "region_code", "last_seen_job_id", "lifecycle", "article_id"),
        Index("ix_listing_mortgage_pending", "mortgage_checked_at", "article_id"),
        Index("ix_listing_move_in", "lifecycle", "is_short_term", "move_in_available_on", "article_id"),
        Index("ix_listing_subway_walk", "lifecycle", "is_short_term", "nearest_subway_walk_minutes", "article_id"),
        Index("ix_listing_management_cost", "lifecycle", "is_short_term", "monthly_management_cost", "article_id"),
        Index("ix_listing_detail_pending", "detail_checked_at", "article_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    article_id = Column(UnsignedBigInt, primary_key=True, autoincrement=False)
    complex_id = Column(
        UnsignedBigInt,
        ForeignKey("complex_current.complex_id", ondelete="RESTRICT"),
        nullable=False,
    )
    region_code = Column(UnsignedBigInt, nullable=False)
    sido_code = Column(
        UnsignedSmallInt,
        Computed("CAST(region_code / 100000000 AS UNSIGNED)", persisted=True),
        nullable=False,
    )
    sigungu_code = Column(
        UnsignedInteger,
        Computed("CAST(region_code / 100000 AS UNSIGNED)", persisted=True),
        nullable=False,
    )
    complex_name = Column(String(120), nullable=False)
    address = Column(String(240), nullable=False)
    construction_year = Column(UnsignedSmallInt, nullable=False, server_default=text("0"))
    household_count = Column(UnsignedMediumInt, nullable=False, server_default=text("0"))
    trade_type = Column(UnsignedTinyInt, nullable=False)
    primary_price = Column(UnsignedBigInt, nullable=False)
    monthly_rent = Column(UnsignedBigInt, nullable=False, server_default=text("0"))
    exclusive_area_x100 = Column(UnsignedInteger, nullable=False, server_default=text("0"))
    supply_area_x100 = Column(UnsignedInteger, nullable=False, server_default=text("0"))
    floor_no = Column(mysql.SMALLINT().with_variant(Integer, "sqlite"), nullable=True)
    total_floor = Column(UnsignedSmallInt, nullable=True)
    floor_band = Column(UnsignedTinyInt, nullable=False, server_default=text("0"))
    direction_code = Column(UnsignedTinyInt, nullable=False, server_default=text("0"))
    mortgage_code = Column(UnsignedTinyInt, nullable=False, server_default=text("0"))
    mortgage_checked_at = Column(DateTime6, nullable=True)
    is_top_floor = Column(Boolean, nullable=False, server_default=text("0"))
    is_short_term = Column(Boolean, nullable=False, server_default=text("0"))
    is_direct_trade = Column(Boolean, nullable=True)
    is_safe_lessor_hug = Column(Boolean, nullable=True)
    room_count = Column(UnsignedTinyInt, nullable=True)
    bathroom_count = Column(UnsignedTinyInt, nullable=True)
    parking_possible = Column(Boolean, nullable=True)
    parking_per_household_x100 = Column(UnsignedInteger, nullable=True)
    monthly_management_cost = Column(UnsignedInteger, nullable=True)
    move_in_available_on = Column(Date, nullable=True)
    nearest_subway_walk_minutes = Column(UnsignedSmallInt, nullable=True)
    detail_checked_at = Column(DateTime6, nullable=True)
    building_name = Column(String(40), nullable=True)
    description = Column(String(1000), nullable=True)
    lifecycle = Column(UnsignedTinyInt, nullable=False, server_default=text("1"))
    miss_count = Column(UnsignedTinyInt, nullable=False, server_default=text("0"))
    state_hash = Column(Hash16, nullable=False)
    last_seen_job_id = Column(UnsignedBigInt, nullable=False)
    first_seen_at = Column(DateTime6, nullable=False)
    last_seen_at = Column(DateTime6, nullable=False)
    last_changed_at = Column(DateTime6, nullable=False)
    removed_at = Column(DateTime6, nullable=True)

    complex = relationship("ComplexCurrent", back_populates="listings")


class ListingHistory(Base):
    """실제 변경만 기록하는 append-only cold history table."""

    __tablename__ = "listing_history"
    __table_args__ = (
        UniqueConstraint("job_id", "article_id", "event_type", name="uk_history_idempotency"),
        Index("ix_history_timeline", "article_id", "occurred_at", "event_id"),
        Index("ix_history_retention", "occurred_at", "event_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    event_id = Column(UnsignedBigInt, primary_key=True, autoincrement=True)
    article_id = Column(UnsignedBigInt, nullable=False)
    complex_id = Column(UnsignedBigInt, nullable=False)
    job_id = Column(UnsignedBigInt, nullable=False)
    event_type = Column(UnsignedTinyInt, nullable=False)
    change_mask = Column(UnsignedInteger, nullable=False, server_default=text("0"))
    primary_price = Column(UnsignedBigInt, nullable=True)
    monthly_rent = Column(UnsignedBigInt, nullable=True)
    lifecycle = Column(UnsignedTinyInt, nullable=True)
    mortgage_code = Column(UnsignedTinyInt, nullable=True)
    floor_no = Column(mysql.SMALLINT().with_variant(Integer, "sqlite"), nullable=True)
    total_floor = Column(UnsignedSmallInt, nullable=True)
    direction_code = Column(UnsignedTinyInt, nullable=True)
    state_hash = Column(Hash16, nullable=False)
    occurred_at = Column(DateTime6, nullable=False)


class CrawlJob(Base):
    """SITE_A 수집만 큐잉하는 lease 기반 작업 테이블."""

    __tablename__ = "crawl_job"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uk_job_dedupe"),
        Index("ix_job_claim", "status", "available_at", "priority", "job_id"),
        Index("ix_job_reap", "status", "lease_expires_at", "job_id"),
        Index("ix_job_recent", "created_at", "job_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    job_id = Column(UnsignedBigInt, primary_key=True, autoincrement=True)
    dedupe_key = Column(String(160), nullable=False)
    status = Column(UnsignedTinyInt, nullable=False, server_default=text("1"))
    priority = Column(UnsignedSmallInt, nullable=False, server_default=text("100"))
    available_at = Column(DateTime6, nullable=False)
    attempt = Column(UnsignedTinyInt, nullable=False, server_default=text("0"))
    max_attempts = Column(UnsignedTinyInt, nullable=False, server_default=text("3"))
    lease_token = Column(String(64), nullable=True)
    lease_owner = Column(String(120), nullable=True)
    lease_expires_at = Column(DateTime6, nullable=True)
    heartbeat_at = Column(DateTime6, nullable=True)
    scope_level = Column(UnsignedTinyInt, nullable=False)
    scope_code = Column(UnsignedBigInt, nullable=False)
    fetched_count = Column(UnsignedInteger, nullable=False, server_default=text("0"))
    committed_count = Column(UnsignedInteger, nullable=False, server_default=text("0"))
    created_count = Column(UnsignedInteger, nullable=False, server_default=text("0"))
    updated_count = Column(UnsignedInteger, nullable=False, server_default=text("0"))
    rejected_count = Column(UnsignedInteger, nullable=False, server_default=text("0"))
    removed_count = Column(UnsignedInteger, nullable=False, server_default=text("0"))
    error_code = Column(String(64), nullable=True)
    error_message = Column(String(512), nullable=True)
    result_json = Column(JSON, nullable=True)
    created_at = Column(DateTime6, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    started_at = Column(DateTime6, nullable=True)
    finished_at = Column(DateTime6, nullable=True)
    updated_at = Column(DateTime6, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class CrawlScope(Base):
    """동 단위 수집 완전성과 재시도를 job과 함께 보존한다."""

    __tablename__ = "crawl_scope"
    __table_args__ = (
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    job_id = Column(UnsignedBigInt, ForeignKey("crawl_job.job_id", ondelete="CASCADE"), primary_key=True)
    region_code = Column(UnsignedBigInt, primary_key=True)
    status = Column(UnsignedTinyInt, nullable=False, server_default=text("1"))
    total_pages = Column(UnsignedSmallInt, nullable=False, server_default=text("0"))
    done_pages = Column(UnsignedSmallInt, nullable=False, server_default=text("0"))
    failed_pages = Column(UnsignedSmallInt, nullable=False, server_default=text("0"))
    fetched_count = Column(UnsignedInteger, nullable=False, server_default=text("0"))
    committed_count = Column(UnsignedInteger, nullable=False, server_default=text("0"))
    rejected_count = Column(UnsignedInteger, nullable=False, server_default=text("0"))
    is_truncated = Column(Boolean, nullable=False, server_default=text("0"))
    error_code = Column(String(64), nullable=True)
    error_message = Column(String(512), nullable=True)
    started_at = Column(DateTime6, nullable=True)
    finished_at = Column(DateTime6, nullable=True)


class UserAccount(Base):
    """간소화 회원가입 및 인증을 위한 사용자 계정 모델."""

    __tablename__ = "user_account"
    __table_args__ = (
        Index("ux_user_username", "username", unique=True),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id = Column(UnsignedInteger, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, server_default=text("'USER'"), default="USER")
    created_at = Column(DateTime6, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    preference = relationship("UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserPreference(Base):
    """사용자의 즐겨찾기, 필터링 및 대출 자격 설정을 보존하는 모델."""

    __tablename__ = "user_preference"
    __table_args__ = (
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    user_id = Column(UnsignedInteger, ForeignKey("user_account.id", ondelete="CASCADE"), primary_key=True)
    favorites_json = Column(JSON, nullable=True)
    filters_json = Column(JSON, nullable=True)
    loan_profile_json = Column(JSON, nullable=True)
    updated_at = Column(DateTime6, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    user = relationship("UserAccount", back_populates="preference")

