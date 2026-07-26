from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_batch_writer import IncomingListing, ListingBatchWriter
from realty_radar.infrastructure.database.models import Base, CrawlJob, ListingCurrent, ListingHistory


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _job(job_id: int, dedupe_key: str) -> CrawlJob:
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    return CrawlJob(
        job_id=job_id,
        dedupe_key=dedupe_key,
        status=1,
        scope_level=3,
        scope_code=1150010200,
        available_at=now,
        created_at=now,
        updated_at=now,
    )


def _incoming(article_id: int, price: int = 500_000_000) -> IncomingListing:
    return IncomingListing(
        article_id=article_id,
        complex_id=1001,
        region_code=1150010200,
        complex_name="테스트 아파트",
        normalized_complex_name="테스트아파트",
        address="서울특별시 강서구 테스트로 1",
        trade_type=1,
        primary_price=price,
        exclusive_area_x100=8497,
        supply_area_x100=11000,
        floor_no=10,
        total_floor=20,
        floor_band=3,
        direction_code=1,
        mortgage_code=0,
        building_name="101동",
        description="테스트 매물",
    )


def test_500_row_replay_does_not_duplicate_current_or_history():
    session = _session()
    session.add_all([_job(1, "dong:1150010200:1"), _job(2, "dong:1150010200:2")])
    session.commit()
    writer = ListingBatchWriter(session)
    batch = [_incoming(10_000 + index) for index in range(500)]

    first = writer.commit_batch(job_id=1, rows=batch)
    assert first.created_count == 500
    assert first.updated_count == 0
    assert session.scalar(select(func.count()).select_from(ListingCurrent)) == 500
    assert session.scalar(select(func.count()).select_from(ListingHistory)) == 0

    replay = writer.commit_batch(job_id=1, rows=batch)
    assert replay.created_count == 0
    assert replay.updated_count == 0
    assert session.scalar(select(func.count()).select_from(ListingCurrent)) == 500
    assert session.scalar(select(func.count()).select_from(ListingHistory)) == 0

    changed = list(batch)
    changed[0] = _incoming(10_000, price=490_000_000)
    update = writer.commit_batch(job_id=2, rows=changed)
    assert update.created_count == 0
    assert update.updated_count == 1
    assert session.scalar(select(func.count()).select_from(ListingHistory)) == 1

    repeated_update = writer.commit_batch(job_id=2, rows=changed)
    assert repeated_update.updated_count == 0
    assert session.scalar(select(func.count()).select_from(ListingHistory)) == 1


def test_listing_recrawl_preserves_completed_mortgage_enrichment():
    session = _session()
    session.add_all([_job(1, "dong:1150010200:1"), _job(2, "dong:1150010200:2")])
    session.commit()
    writer = ListingBatchWriter(session)
    writer.commit_batch(job_id=1, rows=[_incoming(10_000)])
    listing = session.get(ListingCurrent, 10_000)
    listing.mortgage_code = 1
    listing.mortgage_checked_at = datetime.now(timezone.utc).replace(tzinfo=None)
    session.commit()

    writer.commit_batch(job_id=2, rows=[_incoming(10_000, price=490_000_000)])

    refreshed = session.get(ListingCurrent, 10_000)
    assert refreshed.mortgage_code == 1
    assert refreshed.mortgage_checked_at is not None
    history = session.scalar(select(ListingHistory).where(ListingHistory.article_id == 10_000))
    assert history is not None
    assert history.mortgage_code == 1
    assert history.change_mask & 16 == 0
