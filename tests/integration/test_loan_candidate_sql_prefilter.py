from datetime import datetime, timezone
from dataclasses import replace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.domain.loan.entities import ApplicantProfile
from realty_radar.infrastructure.database.models import Base, ListingCurrent


def test_sql_candidate_prefilter_keeps_blank_address_using_safe_capital_limit():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime(2026, 7, 27, tzinfo=timezone.utc)
    session.add(
        ListingCurrent(
            article_id=91,
            complex_id=9,
            region_code=2600000000,
            complex_name="주소 확인 전 단지",
            address="",
            trade_type=2,
            primary_price=300_000_000,
            exclusive_area_x100=8500,
            state_hash=b"0" * 16,
            last_seen_job_id=1,
            first_seen_at=now,
            last_seen_at=now,
            last_changed_at=now,
        )
    )
    session.commit()

    result = ListingSearchService(session, cursor_secret="test-secret").search_listings(
        ListingSearchFilter(only_eligible_loans=True),
        applicant=ApplicantProfile(annual_income=50_000_000),
    )

    assert [listing.article_id for listing in result.items] == [91]


def test_separate_candidate_streams_merge_without_cursor_gaps_or_duplicates():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime(2026, 7, 27, tzinfo=timezone.utc)
    for article_id, trade_type, price in (
        (101, 1, 100_000_000),
        (102, 2, 50_000_000),
        (103, 3, 60_000_000),
        (104, 4, 70_000_000),
    ):
        session.add(
            ListingCurrent(
                article_id=article_id,
                complex_id=10,
                region_code=1150010200,
                complex_name="후보 병합 단지",
                address="서울특별시 강서구",
                trade_type=trade_type,
                primary_price=price,
                exclusive_area_x100=8400,
                state_hash=bytes([article_id]) * 16,
                last_seen_job_id=1,
                first_seen_at=now,
                last_seen_at=now,
                last_changed_at=now,
            )
        )
    session.commit()
    service = ListingSearchService(session, cursor_secret="test-secret")
    filters = ListingSearchFilter(
        only_eligible_loans=True,
        exclude_short_term=False,
        page_size=1,
        sort_by="price_asc",
    )

    article_ids = []
    for _ in range(4):
        page = service.search_listings(
            filters,
            applicant=ApplicantProfile(annual_income=40_000_000),
        )
        article_ids.extend(listing.article_id for listing in page.items)
        filters = replace(filters, cursor=page.next_cursor)

    assert article_ids == [102, 103, 104, 101]
    assert len(set(article_ids)) == 4
