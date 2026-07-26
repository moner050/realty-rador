"""SITE_A 수집 결과를 batch 단위로 현재 상태와 변경 이력에 반영한다."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import md5
from typing import Iterable

from sqlalchemy import case, select, text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from realty_radar.infrastructure.database.models import CrawlJob, ListingCurrent, ListingHistory
from realty_radar.infrastructure.database.models.v2 import ComplexCurrent


LIFECYCLE_ACTIVE = 1
LIFECYCLE_STALE = 2
LIFECYCLE_REMOVED = 3

HISTORY_UPDATED = 1
HISTORY_STALE = 2
HISTORY_REMOVED = 3
HISTORY_REACTIVATED = 4
HISTORY_MORTGAGE_ENRICHED = 5

CHANGE_PRICE = 1
CHANGE_MONTHLY_RENT = 2
CHANGE_FLOOR = 4
CHANGE_DIRECTION = 8
CHANGE_MORTGAGE = 16
CHANGE_DESCRIPTION = 32
CHANGE_LIFECYCLE = 64


def utc_now() -> datetime:
    """MySQL DATETIME(6)에 저장할 timezone-naive UTC 시각을 반환한다."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_parts(*values: object) -> bytes:
    encoded = "\x1f".join("" if value is None else str(value) for value in values).encode("utf-8")
    return md5(encoded, usedforsecurity=False).digest()


@dataclass(frozen=True, slots=True)
class IncomingListing:
    """SITE_A article API에서 검증·정규화된 저장 전용 값 객체."""

    article_id: int
    complex_id: int
    region_code: int
    complex_name: str
    normalized_complex_name: str
    address: str
    trade_type: int
    primary_price: int
    monthly_rent: int = 0
    exclusive_area_x100: int = 0
    supply_area_x100: int = 0
    floor_no: int | None = None
    total_floor: int | None = None
    floor_band: int = 0
    direction_code: int = 0
    mortgage_code: int = 0
    is_top_floor: bool = False
    is_short_term: bool = False
    building_name: str | None = None
    description: str | None = None
    construction_year: int = 0
    household_count: int = 0

    @property
    def state_hash(self) -> bytes:
        return _hash_parts(
            self.complex_id,
            self.region_code,
            self.complex_name,
            self.address,
            self.construction_year,
            self.household_count,
            self.trade_type,
            self.primary_price,
            self.monthly_rent,
            self.exclusive_area_x100,
            self.supply_area_x100,
            self.floor_no,
            self.total_floor,
            self.floor_band,
            self.direction_code,
            self.mortgage_code,
            self.is_top_floor,
            self.is_short_term,
            self.building_name,
            self.description,
        )

    @property
    def complex_state_hash(self) -> bytes:
        return _hash_parts(
            self.complex_id,
            self.region_code,
            self.complex_name,
            self.normalized_complex_name,
            self.address,
            self.construction_year,
            self.household_count,
        )

    def validate(self) -> None:
        if not all(isinstance(value, int) and value > 0 for value in (self.article_id, self.complex_id, self.region_code)):
            raise ValueError("article_id, complex_id, region_code must be positive integers")
        if not self.complex_name or not self.normalized_complex_name or not self.address:
            raise ValueError("complex_name, normalized_complex_name, address are required")
        if self.trade_type <= 0 or self.primary_price < 0:
            raise ValueError("trade_type must be positive and primary_price cannot be negative")

    def listing_values(self, job_id: int, observed_at: datetime) -> dict[str, object]:
        return {
            "article_id": self.article_id,
            "complex_id": self.complex_id,
            "region_code": self.region_code,
            "complex_name": self.complex_name,
            "address": self.address,
            "construction_year": self.construction_year,
            "household_count": self.household_count,
            "trade_type": self.trade_type,
            "primary_price": self.primary_price,
            "monthly_rent": self.monthly_rent,
            "exclusive_area_x100": self.exclusive_area_x100,
            "supply_area_x100": self.supply_area_x100,
            "floor_no": self.floor_no,
            "total_floor": self.total_floor,
            "floor_band": self.floor_band,
            "direction_code": self.direction_code,
            "mortgage_code": self.mortgage_code,
            "is_top_floor": self.is_top_floor,
            "is_short_term": self.is_short_term,
            "building_name": self.building_name,
            "description": self.description,
            "lifecycle": LIFECYCLE_ACTIVE,
            "miss_count": 0,
            "state_hash": self.state_hash,
            "last_seen_job_id": job_id,
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
            "last_changed_at": observed_at,
            "removed_at": None,
        }

    def complex_values(self, observed_at: datetime) -> dict[str, object]:
        return {
            "complex_id": self.complex_id,
            "region_code": self.region_code,
            "name": self.complex_name,
            "normalized_name": self.normalized_complex_name,
            "address": self.address,
            "construction_year": self.construction_year,
            "household_count": self.household_count,
            "state_hash": self.complex_state_hash,
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
            "updated_at": observed_at,
        }


@dataclass(frozen=True, slots=True)
class BatchCommitResult:
    fetched_count: int
    committed_count: int
    created_count: int
    updated_count: int
    rejected_count: int


class ListingBatchWriter:
    """임시 staging table을 이용해 SITE_A batch를 한 번에 저장한다.

    MySQL에서는 연결별 ``incoming_listing`` temporary table을 재사용한다. SQLite
    경로는 단위 테스트를 위한 동등한 set-based upsert이며 운영에서 사용하지 않는다.
    """

    def __init__(self, session: Session):
        self.session = session

    def commit_batch(self, job_id: int, rows: Iterable[IncomingListing], observed_at: datetime | None = None) -> BatchCommitResult:
        now = observed_at or utc_now()
        accepted: dict[int, IncomingListing] = {}
        rejected = 0
        for row in rows:
            try:
                row.validate()
            except ValueError:
                rejected += 1
                continue
            accepted[row.article_id] = row

        batch = list(accepted.values())
        if not batch:
            self._increment_job_counts(job_id, 0, 0, 0, 0, rejected)
            return BatchCommitResult(0, 0, 0, 0, rejected)

        if self.session.bind is None:
            raise RuntimeError("ListingBatchWriter needs a bound database session")

        if self.session.bind.dialect.name == "mysql":
            created, updated = self._commit_mysql(job_id, batch, now)
        else:
            created, updated = self._commit_sqlite(job_id, batch, now)

        self._increment_job_counts(job_id, len(batch), len(batch), created, updated, rejected)
        return BatchCommitResult(len(batch), len(batch), created, updated, rejected)

    def _commit_sqlite(self, job_id: int, rows: list[IncomingListing], now: datetime) -> tuple[int, int]:
        article_ids = [row.article_id for row in rows]
        existing = {
            listing.article_id: listing
            for listing in self.session.scalars(select(ListingCurrent).where(ListingCurrent.article_id.in_(article_ids))).all()
        }
        created = sum(article_id not in existing for article_id in article_ids)
        changed = [
            row
            for row in rows
            if (old := existing.get(row.article_id)) is not None
            and (old.state_hash != row.state_hash or old.lifecycle != LIFECYCLE_ACTIVE)
        ]

        complex_rows = {row.complex_id: row.complex_values(now) for row in rows}
        complex_stmt = sqlite_insert(ComplexCurrent).values(list(complex_rows.values()))
        excluded_complex = complex_stmt.excluded
        self.session.execute(
            complex_stmt.on_conflict_do_update(
                index_elements=["complex_id"],
                set_={
                    "region_code": excluded_complex.region_code,
                    "name": excluded_complex.name,
                    "normalized_name": excluded_complex.normalized_name,
                    "address": excluded_complex.address,
                    "construction_year": excluded_complex.construction_year,
                    "household_count": excluded_complex.household_count,
                    "state_hash": excluded_complex.state_hash,
                    "last_seen_at": excluded_complex.last_seen_at,
                    "updated_at": case(
                        (ComplexCurrent.state_hash != excluded_complex.state_hash, excluded_complex.updated_at),
                        else_=ComplexCurrent.updated_at,
                    ),
                },
            )
        )

        history_rows = [
            {
                "article_id": row.article_id,
                "complex_id": row.complex_id,
                "job_id": job_id,
                "event_type": HISTORY_REACTIVATED
                if existing[row.article_id].lifecycle != LIFECYCLE_ACTIVE
                else HISTORY_UPDATED,
                "change_mask": self._change_mask(
                    existing[row.article_id], row, preserve_enriched_mortgage=existing[row.article_id].mortgage_checked_at is not None
                ),
                "primary_price": row.primary_price,
                "monthly_rent": row.monthly_rent,
                "lifecycle": LIFECYCLE_ACTIVE,
                "mortgage_code": (
                    existing[row.article_id].mortgage_code
                    if existing[row.article_id].mortgage_checked_at is not None
                    else row.mortgage_code
                ),
                "floor_no": row.floor_no,
                "total_floor": row.total_floor,
                "direction_code": row.direction_code,
                "state_hash": row.state_hash,
                "occurred_at": now,
            }
            for row in changed
        ]
        if history_rows:
            history_stmt = sqlite_insert(ListingHistory).values(history_rows)
            self.session.execute(
                history_stmt.on_conflict_do_nothing(index_elements=["job_id", "article_id", "event_type"])
            )

        listing_stmt = sqlite_insert(ListingCurrent).values([row.listing_values(job_id, now) for row in rows])
        excluded_listing = listing_stmt.excluded
        update_values = {
            column: getattr(excluded_listing, column)
            for column in (
                "complex_id",
                "region_code",
                "complex_name",
                "address",
                "construction_year",
                "household_count",
                "trade_type",
                "primary_price",
                "monthly_rent",
                "exclusive_area_x100",
                "supply_area_x100",
                "floor_no",
                "total_floor",
                "floor_band",
                "direction_code",
                "is_top_floor",
                "is_short_term",
                "building_name",
                "description",
                "state_hash",
                "last_seen_job_id",
                "last_seen_at",
            )
        }
        update_values.update(
            {
                "lifecycle": LIFECYCLE_ACTIVE,
                "miss_count": 0,
                "removed_at": None,
                "last_changed_at": case(
                    (
                        (ListingCurrent.state_hash != excluded_listing.state_hash)
                        | (ListingCurrent.lifecycle != LIFECYCLE_ACTIVE),
                        excluded_listing.last_seen_at,
                    ),
                    else_=ListingCurrent.last_changed_at,
                ),
            }
        )
        self.session.execute(
            listing_stmt.on_conflict_do_update(index_elements=["article_id"], set_=update_values)
        )
        self.session.commit()
        return created, len(changed)

    def _commit_mysql(self, job_id: int, rows: list[IncomingListing], now: datetime) -> tuple[int, int]:
        connection = self.session.connection()
        self._ensure_mysql_staging_table(connection)
        connection.execute(text("DELETE FROM incoming_listing"))
        stage_rows = [self._stage_values(row, now) for row in rows]
        connection.execute(
            text(
                """
                INSERT INTO incoming_listing (
                    article_id, complex_id, region_code, complex_name, normalized_complex_name,
                    address, construction_year, household_count, trade_type, primary_price,
                    monthly_rent, exclusive_area_x100, supply_area_x100, floor_no, total_floor,
                    floor_band, direction_code, mortgage_code, is_top_floor, is_short_term,
                    building_name, description, listing_state_hash, complex_state_hash, observed_at
                ) VALUES (
                    :article_id, :complex_id, :region_code, :complex_name, :normalized_complex_name,
                    :address, :construction_year, :household_count, :trade_type, :primary_price,
                    :monthly_rent, :exclusive_area_x100, :supply_area_x100, :floor_no, :total_floor,
                    :floor_band, :direction_code, :mortgage_code, :is_top_floor, :is_short_term,
                    :building_name, :description, :listing_state_hash, :complex_state_hash, :observed_at
                )
                """
            ),
            stage_rows,
        )

        created = int(
            connection.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM incoming_listing incoming
                    LEFT JOIN listing_current current ON current.article_id = incoming.article_id
                    WHERE current.article_id IS NULL
                    """
                )
            )
            or 0
        )
        updated = int(
            connection.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM incoming_listing incoming
                    JOIN listing_current current ON current.article_id = incoming.article_id
                    WHERE current.state_hash <> incoming.listing_state_hash
                       OR current.lifecycle <> :active
                    """
                ),
                {"active": LIFECYCLE_ACTIVE},
            )
            or 0
        )

        connection.execute(
            text(
                """
                INSERT INTO complex_current (
                    complex_id, region_code, name, normalized_name, address,
                    construction_year, household_count, state_hash,
                    first_seen_at, last_seen_at, updated_at
                )
                SELECT
                    complex_id, MIN(region_code), MIN(complex_name), MIN(normalized_complex_name), MIN(address),
                    MIN(construction_year), MIN(household_count), MIN(complex_state_hash),
                    MIN(observed_at), MAX(observed_at), MAX(observed_at)
                FROM incoming_listing
                GROUP BY complex_id
                ON DUPLICATE KEY UPDATE
                    region_code = VALUES(region_code),
                    name = VALUES(name),
                    normalized_name = VALUES(normalized_name),
                    address = VALUES(address),
                    construction_year = VALUES(construction_year),
                    household_count = VALUES(household_count),
                    last_seen_at = VALUES(last_seen_at),
                    updated_at = IF(state_hash <> VALUES(state_hash), VALUES(updated_at), updated_at),
                    state_hash = VALUES(state_hash)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT IGNORE INTO listing_history (
                    article_id, complex_id, job_id, event_type, change_mask, primary_price,
                    monthly_rent, lifecycle, mortgage_code, floor_no, total_floor, direction_code,
                    state_hash, occurred_at
                )
                SELECT
                    incoming.article_id,
                    incoming.complex_id,
                    :job_id,
                    CASE WHEN current.lifecycle <> :active THEN :reactivated ELSE :updated END,
                    (CASE WHEN current.primary_price <> incoming.primary_price THEN :price_mask ELSE 0 END)
                    | (CASE WHEN current.monthly_rent <> incoming.monthly_rent THEN :rent_mask ELSE 0 END)
                    | (CASE WHEN COALESCE(current.floor_no, -999) <> COALESCE(incoming.floor_no, -999)
                              OR COALESCE(current.total_floor, 0) <> COALESCE(incoming.total_floor, 0)
                           THEN :floor_mask ELSE 0 END)
                    | (CASE WHEN current.direction_code <> incoming.direction_code THEN :direction_mask ELSE 0 END)
                    | (CASE WHEN current.lifecycle <> :active THEN :lifecycle_mask ELSE 0 END),
                    incoming.primary_price, incoming.monthly_rent, :active, current.mortgage_code,
                    incoming.floor_no, incoming.total_floor, incoming.direction_code,
                    incoming.listing_state_hash, incoming.observed_at
                FROM incoming_listing incoming
                JOIN listing_current current ON current.article_id = incoming.article_id
                WHERE current.state_hash <> incoming.listing_state_hash
                   OR current.lifecycle <> :active
                """
            ),
            {
                "job_id": job_id,
                "active": LIFECYCLE_ACTIVE,
                "removed": LIFECYCLE_REMOVED,
                "updated": HISTORY_UPDATED,
                "reactivated": HISTORY_REACTIVATED,
                "price_mask": CHANGE_PRICE,
                "rent_mask": CHANGE_MONTHLY_RENT,
                "floor_mask": CHANGE_FLOOR,
                "direction_mask": CHANGE_DIRECTION,
                "lifecycle_mask": CHANGE_LIFECYCLE,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO listing_current (
                    article_id, complex_id, region_code, complex_name, address, construction_year,
                    household_count, trade_type, primary_price, monthly_rent, exclusive_area_x100,
                    supply_area_x100, floor_no, total_floor, floor_band, direction_code, mortgage_code,
                    is_top_floor, is_short_term, building_name, description, lifecycle, miss_count,
                    state_hash, last_seen_job_id, first_seen_at, last_seen_at, last_changed_at, removed_at
                )
                SELECT
                    article_id, complex_id, region_code, complex_name, address, construction_year,
                    household_count, trade_type, primary_price, monthly_rent, exclusive_area_x100,
                    supply_area_x100, floor_no, total_floor, floor_band, direction_code, mortgage_code,
                    is_top_floor, is_short_term, building_name, description, :active, 0,
                    listing_state_hash, :job_id, observed_at, observed_at, observed_at, NULL
                FROM incoming_listing
                ON DUPLICATE KEY UPDATE
                    last_changed_at = IF(state_hash <> VALUES(state_hash) OR lifecycle <> :active,
                                          VALUES(last_seen_at), last_changed_at),
                    complex_id = VALUES(complex_id),
                    region_code = VALUES(region_code),
                    complex_name = VALUES(complex_name),
                    address = VALUES(address),
                    construction_year = VALUES(construction_year),
                    household_count = VALUES(household_count),
                    trade_type = VALUES(trade_type),
                    primary_price = VALUES(primary_price),
                    monthly_rent = VALUES(monthly_rent),
                    exclusive_area_x100 = VALUES(exclusive_area_x100),
                    supply_area_x100 = VALUES(supply_area_x100),
                    floor_no = VALUES(floor_no),
                    total_floor = VALUES(total_floor),
                    floor_band = VALUES(floor_band),
                    direction_code = VALUES(direction_code),
                    is_top_floor = VALUES(is_top_floor),
                    is_short_term = VALUES(is_short_term),
                    building_name = VALUES(building_name),
                    description = VALUES(description),
                    lifecycle = :active,
                    miss_count = 0,
                    state_hash = VALUES(state_hash),
                    last_seen_job_id = VALUES(last_seen_job_id),
                    last_seen_at = VALUES(last_seen_at),
                    removed_at = NULL
                """
            ),
            {"active": LIFECYCLE_ACTIVE, "job_id": job_id},
        )
        self.session.commit()
        return created, updated

    def _increment_job_counts(
        self,
        job_id: int,
        fetched: int,
        committed: int,
        created: int,
        updated: int,
        rejected: int,
    ) -> None:
        self.session.execute(
            update(CrawlJob)
            .where(CrawlJob.job_id == job_id)
            .values(
                fetched_count=CrawlJob.fetched_count + fetched,
                committed_count=CrawlJob.committed_count + committed,
                created_count=CrawlJob.created_count + created,
                updated_count=CrawlJob.updated_count + updated,
                rejected_count=CrawlJob.rejected_count + rejected,
                updated_at=utc_now(),
            )
        )
        self.session.commit()

    @staticmethod
    def _change_mask(
        current: ListingCurrent, incoming: IncomingListing, *, preserve_enriched_mortgage: bool = False
    ) -> int:
        mask = 0
        if current.primary_price != incoming.primary_price:
            mask |= CHANGE_PRICE
        if current.monthly_rent != incoming.monthly_rent:
            mask |= CHANGE_MONTHLY_RENT
        if current.floor_no != incoming.floor_no or current.total_floor != incoming.total_floor:
            mask |= CHANGE_FLOOR
        if current.direction_code != incoming.direction_code:
            mask |= CHANGE_DIRECTION
        if not preserve_enriched_mortgage and current.mortgage_code != incoming.mortgage_code:
            mask |= CHANGE_MORTGAGE
        if current.description != incoming.description:
            mask |= CHANGE_DESCRIPTION
        if current.lifecycle != LIFECYCLE_ACTIVE:
            mask |= CHANGE_LIFECYCLE
        return mask

    @staticmethod
    def _stage_values(row: IncomingListing, observed_at: datetime) -> dict[str, object]:
        values = row.listing_values(job_id=0, observed_at=observed_at)
        values.update(
            {
                "normalized_complex_name": row.normalized_complex_name,
                "listing_state_hash": row.state_hash,
                "complex_state_hash": row.complex_state_hash,
                "observed_at": observed_at,
            }
        )
        values.pop("state_hash")
        values.pop("last_seen_job_id")
        values.pop("first_seen_at")
        values.pop("last_seen_at")
        values.pop("last_changed_at")
        values.pop("lifecycle")
        values.pop("miss_count")
        values.pop("removed_at")
        return values

    @staticmethod
    def _ensure_mysql_staging_table(connection) -> None:
        connection.execute(
            text(
                """
                CREATE TEMPORARY TABLE IF NOT EXISTS incoming_listing (
                    article_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
                    complex_id BIGINT UNSIGNED NOT NULL,
                    region_code BIGINT UNSIGNED NOT NULL,
                    complex_name VARCHAR(120) NOT NULL,
                    normalized_complex_name VARCHAR(120) NOT NULL,
                    address VARCHAR(240) NOT NULL,
                    construction_year SMALLINT UNSIGNED NOT NULL,
                    household_count MEDIUMINT UNSIGNED NOT NULL,
                    trade_type TINYINT UNSIGNED NOT NULL,
                    primary_price BIGINT UNSIGNED NOT NULL,
                    monthly_rent BIGINT UNSIGNED NOT NULL,
                    exclusive_area_x100 INT UNSIGNED NOT NULL,
                    supply_area_x100 INT UNSIGNED NOT NULL,
                    floor_no SMALLINT NULL,
                    total_floor SMALLINT UNSIGNED NULL,
                    floor_band TINYINT UNSIGNED NOT NULL,
                    direction_code TINYINT UNSIGNED NOT NULL,
                    mortgage_code TINYINT UNSIGNED NOT NULL,
                    is_top_floor BOOLEAN NOT NULL,
                    is_short_term BOOLEAN NOT NULL,
                    building_name VARCHAR(40) NULL,
                    description VARCHAR(1000) NULL,
                    listing_state_hash BINARY(16) NOT NULL,
                    complex_state_hash BINARY(16) NOT NULL,
                    observed_at DATETIME(6) NOT NULL
                ) ENGINE=InnoDB
                """
            )
        )
