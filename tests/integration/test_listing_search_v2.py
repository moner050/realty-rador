from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.infrastructure.database.models import Base, ComplexCurrent, ListingCurrent


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(session):
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    for complex_id, name, households in ((1001, "래미안 테스트", 1200), (1002, "푸르지오 테스트", 800)):
        session.add(
            ComplexCurrent(
                complex_id=complex_id,
                region_code=1150010200,
                name=name,
                normalized_name=name.replace(" ", ""),
                address="서울특별시 강서구 테스트로 1",
                household_count=households,
                state_hash=bytes([complex_id % 256]) * 16,
                first_seen_at=now,
                last_seen_at=now,
                updated_at=now,
            )
        )
    prices = (500_000_000, 550_000_000, 600_000_000, 650_000_000)
    for offset, price in enumerate(prices):
        session.add(
            ListingCurrent(
                article_id=2001 + offset,
                complex_id=1001 if offset < 2 else 1002,
                region_code=1150010200,
                complex_name="래미안 테스트" if offset < 2 else "푸르지오 테스트",
                address="서울특별시 강서구 테스트로 1",
                household_count=1200 if offset < 2 else 800,
                trade_type=1,
                primary_price=price,
                exclusive_area_x100=8497,
                state_hash=bytes([offset]) * 16,
                last_seen_job_id=1,
                first_seen_at=now + timedelta(seconds=offset),
                last_seen_at=now,
                last_changed_at=now,
            )
        )
    session.commit()


def test_price_keyset_cursor_has_no_duplicates_or_count_query():
    session = _session()
    _seed(session)
    service = ListingSearchService(session, cursor_secret="test-secret")
    filters = ListingSearchFilter(sigungu_code=11500, sort_by="price_asc", page_size=2)

    first = service.search_listings(filters)
    second = service.search_listings(ListingSearchFilter(sigungu_code=11500, sort_by="price_asc", page_size=2, cursor=first.next_cursor))

    assert [item.article_id for item in first.items + second.items] == [2001, 2002, 2003, 2004]
    assert first.has_more is True
    assert second.has_more is False
    assert not hasattr(first, "total_count")


def test_cursor_cannot_be_reused_with_different_filters():
    session = _session()
    _seed(session)
    service = ListingSearchService(session, cursor_secret="test-secret")
    first = service.search_listings(ListingSearchFilter(sort_by="price_asc", page_size=1))

    with pytest.raises(ValueError, match="cursor"):
        service.search_listings(
            ListingSearchFilter(trade_type=2, sort_by="price_asc", page_size=1, cursor=first.next_cursor)
        )


def test_complex_grouping_uses_group_rows_and_second_listing_query():
    session = _session()
    _seed(session)
    service = ListingSearchService(session, cursor_secret="test-secret")

    result = service.search_listings(ListingSearchFilter(group_by_complex=True, sort_by="price_asc", page_size=1))

    assert result.is_grouped is True
    assert len(result.grouped_items) == 1
    assert result.grouped_items[0].complex_id == 1001
    assert [item.article_id for item in result.grouped_items[0].listings] == [2001, 2002]
    assert result.has_more is True
