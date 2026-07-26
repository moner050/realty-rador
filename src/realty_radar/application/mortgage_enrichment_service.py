"""Low-rate SITE_A detail enrichment for explicit mortgage wording only."""
from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from realty_radar.application.listing_batch_writer import CHANGE_MORTGAGE, HISTORY_MORTGAGE_ENRICHED, utc_now
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


class MortgageEnrichmentRunner:
    """Resumable detail worker; failed requests stay pending for a later run."""

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

    async def run_once(self, *, batch_size: int = 100) -> int:
        """Run the first pending batch; callers needing a full sweep use ``run_until_idle``."""
        return (await self._run_batch(batch_size=batch_size, after_article_id=None)).checked_count

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

    async def _run_batch(self, *, batch_size: int, after_article_id: int | None) -> EnrichmentBatch:
        if not 1 <= batch_size <= 500:
            raise ValueError("batch_size must be between 1 and 500")
        with self._session_factory() as db:
            statement = (
                select(ListingCurrent.article_id, ListingCurrent.complex_id)
                .where(ListingCurrent.lifecycle == LIFECYCLE_ACTIVE, ListingCurrent.mortgage_checked_at.is_(None))
                .order_by(ListingCurrent.article_id)
                .limit(batch_size)
            )
            if after_article_id is not None:
                statement = statement.where(ListingCurrent.article_id > after_article_id)
            candidates = [
                (row.article_id, row.complex_id)
                for row in db.execute(statement).all()
            ]
        last_candidate_id = candidates[-1][0] if candidates else None
        semaphore = asyncio.Semaphore(self._concurrency)

        async def fetch(candidate: tuple[int, int]) -> tuple[int, int] | None:
            article_id, complex_id = candidate
            try:
                async with semaphore:
                    payload = await self._detail_fetcher(article_id, complex_id)
                if not isinstance(payload, dict):
                    return None
                detail = payload.get("articleDetail")
                fields = detail if isinstance(detail, dict) else payload
                # Only these two fields enter the short-lived classifier input.
                text = " ".join(
                    str(fields.get(key) or "") for key in ("detailDescription", "articleFeatureDescription")
                )
                return article_id, classify_mortgage_text(text)
            except asyncio.CancelledError:
                raise
            except Exception:
                return None

        responses = await asyncio.gather(*(fetch(candidate) for candidate in candidates))
        resolved = [item for item in responses if item is not None]
        if not resolved:
            return EnrichmentBatch(checked_count=0, last_candidate_id=last_candidate_id)
        now = utc_now()
        with self._session_factory() as db:
            updates: list[dict[str, Any]] = []
            history: list[ListingHistory] = []
            for article_id, code in resolved:
                listing = db.get(ListingCurrent, article_id)
                if listing is None or listing.mortgage_checked_at is not None:
                    continue
                changed = listing.mortgage_code != code
                updates.append(
                    {
                        "article_id": listing.article_id,
                        "mortgage_code": code,
                        "mortgage_checked_at": now,
                        "last_changed_at": now if changed else listing.last_changed_at,
                    }
                )
                if changed:
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
                            mortgage_code=code,
                            floor_no=listing.floor_no,
                            total_floor=listing.total_floor,
                            direction_code=listing.direction_code,
                            state_hash=listing.state_hash,
                            occurred_at=now,
                        )
                    )
            if updates:
                db.execute(update(ListingCurrent), updates)
            if history:
                db.add_all(history)
            db.commit()
        return EnrichmentBatch(checked_count=len(updates), last_candidate_id=last_candidate_id)


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

    async def fetch(article_id: int, complex_id: int) -> dict[str, Any]:
        payload = await client.get_json(
            f"{NEW_LAND_BASE}/api/articles/{article_id}", params={"complexNo": complex_id}
        )
        return payload if isinstance(payload, dict) else {}

    try:
        return await MortgageEnrichmentRunner(
            session_factory, detail_fetcher=fetch, job_id=job_id, concurrency=concurrency
        ).run_until_idle(batch_size=batch_size, max_batches=max_batches)
    finally:
        await client.aclose()
        await browser.close()
