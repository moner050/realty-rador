"""Low-rate SITE_A detail enrichment for explicit mortgage wording only."""
from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from realty_radar.application.listing_batch_writer import (
    CHANGE_DETAIL,
    CHANGE_MORTGAGE,
    HISTORY_DETAIL_ENRICHED,
    HISTORY_MORTGAGE_ENRICHED,
    utc_now,
)
from realty_radar.crawler.adapters.site_a.http_client import AuthenticationError
from realty_radar.infrastructure.database.models import ListingCurrent, ListingHistory


MORTGAGE_UNKNOWN = 0
MORTGAGE_EXPLICIT_NONE = 1
MORTGAGE_EXPLICIT_EXISTS = 2
LIFECYCLE_ACTIVE = 1

_NONE_PHRASES = ("융자무", "융자금없음", "융자없음", "근저당없음", "대출없음")
_EXISTS_PHRASES = ("융자금있음", "융자있음", "근저당", "채권최고액", "대출있음")


def classify_mortgage_text(value: str) -> int:
    """Return a code without retaining the untrusted SITE_A detail text."""
    normalized = re.sub(r"\s+", "", value)
    if any(phrase in normalized for phrase in _NONE_PHRASES):
        return MORTGAGE_EXPLICIT_NONE
    if any(phrase in normalized for phrase in _EXISTS_PHRASES):
        return MORTGAGE_EXPLICIT_EXISTS
    if re.search(r"융자\d+(?:[%％]|만원|억|원)?", normalized):
        return MORTGAGE_EXPLICIT_EXISTS
    return MORTGAGE_UNKNOWN


DetailFetcher = Callable[[int, int], Any]


@dataclass(frozen=True, slots=True)
class EnrichmentBatch:
    checked_count: int
    last_candidate_id: int | None


@dataclass(frozen=True, slots=True)
class ArticleDetail:
    """Typed values retained from a SITE_A detail response only."""

    mortgage_code: int
    room_count: int | None
    bathroom_count: int | None
    parking_possible: bool | None
    parking_per_household_x100: int | None
    monthly_management_cost: int | None
    move_in_available_on: date | None
    nearest_subway_walk_minutes: int | None


def _detail_fields(payload: dict[str, Any]) -> dict[str, Any]:
    detail = payload.get("articleDetail")
    return detail if isinstance(detail, dict) else payload


def _first_value(fields: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in fields:
            return fields[name]
    return None


def _unsigned_int(value: Any, *, maximum: int) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= maximum else None


def _positive_int_or_none(value: Any, *, maximum: int) -> int | None:
    number = _unsigned_int(value, maximum=maximum)
    return number if number is not None and number > 0 else None


def _nullable_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in {"Y", "YES", "TRUE", "1"}:
            return True
        if normalized in {"N", "NO", "FALSE", "0"}:
            return False
    return None


def _per_household_x100(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        scaled = Decimal(str(value).strip()) * 100
    except (InvalidOperation, TypeError, ValueError):
        return None
    if scaled != scaled.to_integral_value():
        return None
    result = int(scaled)
    return result if 0 <= result <= 100_000 else None


def _date_value(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if re.fullmatch(r"\d{8}", normalized):
        normalized = f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:]}"
    elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        return None
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        return None


def parse_article_detail(payload: dict[str, Any]) -> ArticleDetail:
    """Extract typed detail fields without returning API text or the payload."""
    fields = _detail_fields(payload)
    detail_text = " ".join(
        str(fields.get(name) or "") for name in ("detailDescription", "articleFeatureDescription")
    )
    return ArticleDetail(
        mortgage_code=classify_mortgage_text(detail_text),
        room_count=_unsigned_int(_first_value(fields, "roomCount"), maximum=255),
        bathroom_count=_unsigned_int(_first_value(fields, "bathroomCount"), maximum=255),
        parking_possible=_nullable_bool(
            _first_value(fields, "parkingPossible", "parkingPossibleYn", "parkingPossibleYN")
        ),
        parking_per_household_x100=_per_household_x100(
            _first_value(fields, "parkingPerHousehold", "parkingPerHouseholdCount")
        ),
        monthly_management_cost=_unsigned_int(
            _first_value(fields, "monthlyManagementCost", "managementCost"), maximum=4_294_967_295
        ),
        move_in_available_on=_date_value(
            _first_value(fields, "moveInAvailableDate", "moveInDate", "moveInPossibleYmd")
        ),
        nearest_subway_walk_minutes=_positive_int_or_none(
            _first_value(fields, "nearestSubwayWalkMinutes", "subwayWalkMinutes", "walkingTimeToNearSubway"),
            maximum=65535,
        ),
    )


class MortgageEnrichmentRunner:
    """Resumable SITE_A detail worker; failed requests stay pending for a later run."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        detail_fetcher: DetailFetcher,
        job_id: int,
        concurrency: int = 2,
    ):
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        self._session_factory = session_factory
        self._detail_fetcher = detail_fetcher
        self._job_id = job_id
        self._concurrency = concurrency
        self._claim_token = uuid4().hex

    async def run_once(self, *, batch_size: int = 100, priority_job_id: int | None = None) -> int:
        """Run the first pending batch; callers needing a full sweep use ``run_until_idle``."""
        return (
            await self._run_batch(
                batch_size=batch_size,
                after_article_id=None,
                priority_job_id=priority_job_id,
            )
        ).checked_count

    async def run_until_idle(self, *, batch_size: int = 100, max_batches: int = 100) -> int:
        """Sweep pending active rows with a keyset cursor so one bad row cannot starve later rows."""
        if max_batches < 1:
            raise ValueError("max_batches must be positive")
        after_article_id: int | None = None
        checked = 0
        for _ in range(max_batches):
            batch = await self._run_batch(batch_size=batch_size, after_article_id=after_article_id)
            checked += batch.checked_count
            if batch.last_candidate_id is None:
                break
            after_article_id = batch.last_candidate_id
        return checked

    async def _run_batch(
        self,
        *,
        batch_size: int,
        after_article_id: int | None,
        priority_job_id: int | None = None,
    ) -> EnrichmentBatch:
        if not 1 <= batch_size <= 500:
            raise ValueError("batch_size must be between 1 and 500")
        candidates = self._claim_batch(
            batch_size=batch_size,
            priority_job_id=priority_job_id,
            after_article_id=after_article_id,
        )
        last_candidate_id = candidates[-1][0] if candidates else None
        semaphore = asyncio.Semaphore(self._concurrency)

        async def fetch(candidate: tuple[int, int]) -> tuple[int, ArticleDetail | None]:
            article_id, complex_id = candidate
            try:
                async with semaphore:
                    payload = await self._detail_fetcher(article_id, complex_id)
                if not isinstance(payload, dict):
                    return article_id, None
                return article_id, parse_article_detail(payload)
            except asyncio.CancelledError:
                raise
            except AuthenticationError:
                raise
            except Exception:
                return article_id, None

        tasks = [asyncio.create_task(fetch(candidate)) for candidate in candidates]
        try:
            responses = await asyncio.gather(*tasks)
        except AuthenticationError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._release_claims(article_id for article_id, _ in candidates)
            raise
        resolved = [(article_id, detail) for article_id, detail in responses if detail is not None]
        failed_article_ids = [article_id for article_id, detail in responses if detail is None]
        now = utc_now()
        with self._session_factory() as db:
            successful_writes = 0
            history: list[ListingHistory] = []
            for article_id, detail in resolved:
                listing = db.get(ListingCurrent, article_id)
                if (
                    listing is None
                    or listing.detail_checked_at is not None
                    or listing.detail_claim_token != self._claim_token
                ):
                    continue
                mortgage_changed = listing.mortgage_code != detail.mortgage_code
                detail_changed = any(
                    getattr(listing, name) != getattr(detail, name)
                    for name in (
                        "room_count",
                        "bathroom_count",
                        "parking_possible",
                        "parking_per_household_x100",
                        "monthly_management_cost",
                        "move_in_available_on",
                        "nearest_subway_walk_minutes",
                    )
                )
                wrote = db.execute(
                    update(ListingCurrent)
                    .where(
                        ListingCurrent.article_id == listing.article_id,
                        ListingCurrent.detail_claim_token == self._claim_token,
                    )
                    .values(
                        mortgage_code=detail.mortgage_code,
                        mortgage_checked_at=now,
                        room_count=detail.room_count,
                        bathroom_count=detail.bathroom_count,
                        parking_possible=detail.parking_possible,
                        parking_per_household_x100=detail.parking_per_household_x100,
                        monthly_management_cost=detail.monthly_management_cost,
                        move_in_available_on=detail.move_in_available_on,
                        nearest_subway_walk_minutes=detail.nearest_subway_walk_minutes,
                        detail_checked_at=now,
                        detail_claim_token=None,
                        detail_claimed_at=None,
                        last_changed_at=now if mortgage_changed or detail_changed else listing.last_changed_at,
                    )
                )
                if not wrote.rowcount:
                    continue
                successful_writes += 1
                if mortgage_changed:
                    history.append(
                        ListingHistory(
                            article_id=listing.article_id,
                            complex_id=listing.complex_id,
                            job_id=self._job_id,
                            event_type=HISTORY_MORTGAGE_ENRICHED,
                            change_mask=CHANGE_MORTGAGE,
                            primary_price=listing.primary_price,
                            monthly_rent=listing.monthly_rent,
                            lifecycle=listing.lifecycle,
                            mortgage_code=detail.mortgage_code,
                            floor_no=listing.floor_no,
                            total_floor=listing.total_floor,
                            direction_code=listing.direction_code,
                            state_hash=listing.state_hash,
                            occurred_at=now,
                        )
                    )
                if detail_changed:
                    history.append(
                        ListingHistory(
                            article_id=listing.article_id,
                            complex_id=listing.complex_id,
                            job_id=self._job_id,
                            event_type=HISTORY_DETAIL_ENRICHED,
                            change_mask=CHANGE_DETAIL,
                            primary_price=listing.primary_price,
                            monthly_rent=listing.monthly_rent,
                            lifecycle=listing.lifecycle,
                            mortgage_code=detail.mortgage_code,
                            floor_no=listing.floor_no,
                            total_floor=listing.total_floor,
                            direction_code=listing.direction_code,
                            state_hash=listing.state_hash,
                            occurred_at=now,
                        )
                    )
            if failed_article_ids:
                db.execute(
                    update(ListingCurrent)
                    .where(
                        ListingCurrent.article_id.in_(failed_article_ids),
                        ListingCurrent.detail_claim_token == self._claim_token,
                    )
                    .values(detail_claim_token=None, detail_claimed_at=None)
                )
            if history:
                db.add_all(history)
            db.commit()
        return EnrichmentBatch(checked_count=successful_writes, last_candidate_id=last_candidate_id)

    def _release_claims(self, article_ids) -> None:
        with self._session_factory() as db:
            db.execute(
                update(ListingCurrent)
                .where(
                    ListingCurrent.article_id.in_(article_ids),
                    ListingCurrent.detail_claim_token == self._claim_token,
                )
                .values(detail_claim_token=None, detail_claimed_at=None)
            )
            db.commit()

    def _claim_batch(
        self,
        *,
        batch_size: int,
        priority_job_id: int | None = None,
        after_article_id: int | None = None,
    ) -> list[tuple[int, int]]:
        """Atomically reserve the next unchecked detail rows for this runner."""
        now = utc_now()
        claim_expiry = now - timedelta(minutes=15)
        claim_available = or_(
            ListingCurrent.detail_claim_token.is_(None),
            ListingCurrent.detail_claimed_at < claim_expiry,
        )
        with self._session_factory() as db:
            statement = (
                select(ListingCurrent.article_id, ListingCurrent.complex_id)
                .where(
                    ListingCurrent.lifecycle == LIFECYCLE_ACTIVE,
                    ListingCurrent.detail_checked_at.is_(None),
                    claim_available,
                )
                .order_by(ListingCurrent.article_id)
            )
            if after_article_id is not None:
                statement = statement.where(ListingCurrent.article_id > after_article_id)
            if db.get_bind().dialect.name == "mysql":
                statement = statement.with_for_update(skip_locked=True)

            candidates: list[tuple[int, int]] = []

            def claim(statement_to_claim):
                for row in db.execute(statement_to_claim).all():
                    claimed = db.execute(
                        update(ListingCurrent)
                        .where(
                            ListingCurrent.article_id == row.article_id,
                            ListingCurrent.lifecycle == LIFECYCLE_ACTIVE,
                            ListingCurrent.detail_checked_at.is_(None),
                            claim_available,
                        )
                        .values(detail_claim_token=self._claim_token, detail_claimed_at=now)
                    )
                    if claimed.rowcount:
                        candidates.append((row.article_id, row.complex_id))

            if priority_job_id is not None and after_article_id is None:
                claim(statement.where(ListingCurrent.last_seen_job_id == priority_job_id).limit(batch_size))
            if len(candidates) < batch_size:
                fallback = statement
                if priority_job_id is not None and after_article_id is None:
                    fallback = fallback.where(ListingCurrent.last_seen_job_id != priority_job_id)
                claim(fallback.limit(batch_size - len(candidates)))
            db.commit()
        return candidates


async def run_site_a_mortgage_enrichment(
    session_factory: Callable[[], Session], *, job_id: int, batch_size: int = 100, concurrency: int = 2,
    max_batches: int = 100,
) -> int:
    """One explicit scheduler/CLI entrypoint using the existing bootstrap+httpx path."""
    from realty_radar.crawler.adapters.site_a.adapter import NEW_LAND_BASE
    from realty_radar.crawler.adapters.site_a.bootstrap import NaverAuthBootstrap
    from realty_radar.crawler.adapters.site_a.http_client import NaverHttpClient
    from realty_radar.crawler.base.browser import PlaywrightBrowserManager

    browser = PlaywrightBrowserManager(headless=True)
    client = NaverHttpClient(NaverAuthBootstrap(browser))

    async def fetch(article_id: int, complex_id: int) -> Any:
        return await client.get_json(
            f"{NEW_LAND_BASE}/api/articles/{article_id}", params={"complexNo": complex_id}
        )

    try:
        return await MortgageEnrichmentRunner(
            session_factory, detail_fetcher=fetch, job_id=job_id, concurrency=concurrency
        ).run_until_idle(batch_size=batch_size, max_batches=max_batches)
    finally:
        await client.aclose()
        await browser.close()
