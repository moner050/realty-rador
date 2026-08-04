import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_batch_writer import utc_now
from realty_radar.application.mortgage_enrichment_service import MortgageEnrichmentRunner
from realty_radar.crawler.adapters.site_a.http_client import AuthenticationError, RetryWaitError
from realty_radar.infrastructure.database.models import Base, ComplexCurrent, ListingCurrent, ListingHistory


@pytest.fixture
def session_factory():
    return _session_factory()


def _session_factory(session_class=Session):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=session_class)


async def async_detail_fetcher(article_id: int, complex_id: int):
    return {"articleDetail": {"roomCount": 3}}


async def raising_detail_fetcher(article_id: int, complex_id: int):
    raise RuntimeError("detail endpoint unavailable")


def _complex_id_for(article_id: int) -> int:
    return article_id + 1_000


def _seed_pending_details(session_factory, *, article_ids: list[int], claimed_at=None):
    now = utc_now()
    with session_factory() as session:
        for article_id in article_ids:
            complex_id = _complex_id_for(article_id)
            session.add(
                ComplexCurrent(
                    complex_id=complex_id,
                    region_code=1150010200,
                    name=f"complex-{article_id}",
                    normalized_name=f"complex-{article_id}",
                    address=f"address-{article_id}",
                    state_hash=b"c" * 16,
                    first_seen_at=now,
                    last_seen_at=now,
                    updated_at=now,
                )
            )
            session.add(
                ListingCurrent(
                    article_id=article_id,
                    complex_id=complex_id,
                    region_code=1150010200,
                    complex_name=f"complex-{article_id}",
                    address=f"address-{article_id}",
                    trade_type=1,
                    primary_price=300_000_000,
                    state_hash=article_id.to_bytes(16, "big"),
                    last_seen_job_id=1,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_changed_at=now,
                    detail_claim_token="expired" if claimed_at is not None else None,
                    detail_claimed_at=claimed_at,
                )
            )
        session.commit()


def test_two_runners_claim_disjoint_pending_articles(session_factory):
    _seed_pending_details(session_factory, article_ids=[10, 20])
    first = MortgageEnrichmentRunner(session_factory, detail_fetcher=async_detail_fetcher, job_id=1)
    second = MortgageEnrichmentRunner(session_factory, detail_fetcher=async_detail_fetcher, job_id=1)

    first_claim = first._claim_batch(batch_size=1)
    second_claim = second._claim_batch(batch_size=1)

    assert {first_claim[0][0], second_claim[0][0]} == {10, 20}


def test_failed_detail_fetch_releases_claim_without_marking_checked(session_factory):
    _seed_pending_details(session_factory, article_ids=[10])
    runner = MortgageEnrichmentRunner(session_factory, detail_fetcher=raising_detail_fetcher, job_id=1)

    checked = asyncio.run(runner.run_once(batch_size=1))

    assert checked == 0
    with session_factory() as session:
        listing = session.get(ListingCurrent, 10)
        assert listing.detail_checked_at is None
        assert listing.detail_claim_token is None
        assert listing.detail_claimed_at is None


def test_authentication_failure_propagates_and_releases_unchecked_claim(session_factory):
    _seed_pending_details(session_factory, article_ids=[10])

    async def authentication_failure(article_id: int, complex_id: int):
        raise AuthenticationError("SITE_A bootstrap failed")

    runner = MortgageEnrichmentRunner(session_factory, detail_fetcher=authentication_failure, job_id=1)

    with pytest.raises(AuthenticationError, match="bootstrap failed"):
        asyncio.run(runner.run_until_idle(batch_size=1, max_batches=1))

    with session_factory() as session:
        listing = session.get(ListingCurrent, 10)
        assert listing.detail_checked_at is None
        assert listing.detail_claim_token is None
        assert listing.detail_claimed_at is None


def test_retry_wait_failure_propagates_cancels_sibling_and_releases_unchecked_claims(session_factory):
    _seed_pending_details(session_factory, article_ids=[10, 20])
    sibling_started = asyncio.Event()
    sibling_cancelled = False

    async def retry_wait_failure(article_id: int, complex_id: int):
        nonlocal sibling_cancelled
        if article_id == 10:
            await sibling_started.wait()
            raise RetryWaitError("SITE_A HTTP circuit is open")
        sibling_started.set()
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            sibling_cancelled = True
            raise
        return {"articleDetail": {"roomCount": 3}}

    runner = MortgageEnrichmentRunner(session_factory, detail_fetcher=retry_wait_failure, job_id=1, concurrency=2)

    with pytest.raises(RetryWaitError, match="circuit is open"):
        asyncio.run(runner.run_until_idle(batch_size=2, max_batches=1))

    assert sibling_cancelled is True
    with session_factory() as session:
        listings = list(session.scalars(select(ListingCurrent).order_by(ListingCurrent.article_id)))
        assert all(listing.detail_checked_at is None for listing in listings)
        assert all(listing.detail_claim_token is None for listing in listings)
        assert all(listing.detail_claimed_at is None for listing in listings)


def test_expired_claim_is_claimable_again(session_factory):
    _seed_pending_details(session_factory, article_ids=[10], claimed_at=utc_now() - timedelta(minutes=16))
    runner = MortgageEnrichmentRunner(session_factory, detail_fetcher=async_detail_fetcher, job_id=1)

    assert runner._claim_batch(batch_size=1) == [(10, _complex_id_for(10))]


def test_taken_over_claim_rejects_stale_success_write():
    class TakeoverSession(Session):
        _takeover_done = False

        def get(self, entity, ident, *args, **kwargs):
            listing = super().get(entity, ident, *args, **kwargs)
            if (
                entity is ListingCurrent
                and ident == 10
                and listing is not None
                and listing.detail_claim_token is not None
                and not self._takeover_done
            ):
                self.execute(
                    update(ListingCurrent)
                    .where(ListingCurrent.article_id == 10)
                    .values(detail_claim_token="newer-claim", detail_claimed_at=utc_now())
                    .execution_options(synchronize_session=False)
                )
                self._takeover_done = True
            return listing

    factory = _session_factory(TakeoverSession)
    _seed_pending_details(factory, article_ids=[10])

    async def detail_fetcher(article_id: int, complex_id: int):
        return {"articleDetail": {"roomCount": 9}}

    checked = asyncio.run(MortgageEnrichmentRunner(factory, detail_fetcher=detail_fetcher, job_id=1).run_once(batch_size=1))

    assert checked == 0
    with factory() as session:
        listing = session.get(ListingCurrent, 10)
        assert listing.room_count is None
        assert listing.detail_checked_at is None
        assert listing.detail_claim_token == "newer-claim"
        assert listing.detail_claimed_at is not None
        assert list(session.scalars(select(ListingHistory).where(ListingHistory.article_id == 10))) == []
