"""Low-rate SITE_A detail enrichment for explicit mortgage wording only."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from realty_radar.application.listing_batch_writer import CHANGE_MORTGAGE, HISTORY_UPDATED, utc_now
from realty_radar.infrastructure.database.models import ListingCurrent, ListingHistory


MORTGAGE_UNKNOWN = 0
MORTGAGE_EXPLICIT_NONE = 1
MORTGAGE_EXPLICIT_EXISTS = 2

_NONE_PHRASES = ("융자금 없음", "융자 없음", "융자없음", "근저당 없음", "대출 없음")
_EXISTS_PHRASES = ("융자금 있음", "융자 있음", "융자있음", "근저당 있음", "대출 있음")


def classify_mortgage_text(value: str) -> int:
    """Return a code without retaining the untrusted SITE_A detail text."""
    normalized = " ".join(value.replace("\n", " ").split())
    if any(phrase in normalized for phrase in _NONE_PHRASES):
        return MORTGAGE_EXPLICIT_NONE
    if any(phrase in normalized for phrase in _EXISTS_PHRASES):
        return MORTGAGE_EXPLICIT_EXISTS
    return MORTGAGE_UNKNOWN


DetailFetcher = Callable[[int, int], Any]


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
        if not 1 <= batch_size <= 500:
            raise ValueError("batch_size must be between 1 and 500")
        with self._session_factory() as db:
            candidates = [
                (row.article_id, row.complex_id)
                for row in db.execute(
                    select(ListingCurrent.article_id, ListingCurrent.complex_id)
                    .where(ListingCurrent.mortgage_checked_at.is_(None))
                    .order_by(ListingCurrent.article_id)
                    .limit(batch_size)
                ).all()
            ]
        semaphore = asyncio.Semaphore(self._concurrency)

        async def fetch(candidate: tuple[int, int]) -> tuple[int, int] | None:
            article_id, complex_id = candidate
            try:
                async with semaphore:
                    payload = await self._detail_fetcher(article_id, complex_id)
                if not isinstance(payload, dict):
                    return None
                # Only these two fields enter the short-lived classifier input.
                text = " ".join(
                    str(payload.get(key) or "") for key in ("detailDescription", "articleFeatureDescription")
                )
                return article_id, classify_mortgage_text(text)
            except asyncio.CancelledError:
                raise
            except Exception:
                return None

        responses = await asyncio.gather(*(fetch(candidate) for candidate in candidates))
        resolved = [item for item in responses if item is not None]
        if not resolved:
            return 0
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
                            event_type=HISTORY_UPDATED,
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
        return len(updates)


async def run_site_a_mortgage_enrichment(
    session_factory: Callable[[], Session], *, job_id: int, batch_size: int = 100, concurrency: int = 2
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
        ).run_once(batch_size=batch_size)
    finally:
        await client.aclose()
        await browser.close()
