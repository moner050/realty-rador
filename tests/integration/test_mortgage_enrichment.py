import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.mortgage_enrichment_service import (
    MortgageEnrichmentRunner,
    classify_mortgage_text,
    parse_article_detail,
)
from realty_radar.application.listing_batch_writer import (
    HISTORY_DETAIL_ENRICHED,
    HISTORY_MORTGAGE_ENRICHED,
    HISTORY_UPDATED,
)
from realty_radar.infrastructure.database.models import Base, ComplexCurrent, ListingCurrent, ListingHistory


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with factory() as session:
        session.add(
            ComplexCurrent(
                complex_id=1,
                region_code=1150010200,
                name="테스트",
                normalized_name="테스트",
                address="서울특별시 테스트구",
                state_hash=b"c" * 16,
                first_seen_at=now,
                last_seen_at=now,
                updated_at=now,
            )
        )
        for article_id in (10, 11, 12):
            session.add(
                ListingCurrent(
                    article_id=article_id,
                    complex_id=1,
                    region_code=1150010200,
                    complex_name="테스트",
                    address="서울특별시 테스트구",
                    trade_type=1,
                    primary_price=300_000_000,
                    state_hash=bytes([article_id]) * 16,
                    last_seen_job_id=1,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_changed_at=now,
                )
            )
        session.commit()
    return factory


def test_mortgage_classifier_prefers_explicit_none_over_generic_finance_words():
    assert classify_mortgage_text("융자금 없음") == 1
    assert classify_mortgage_text("융자 있음") == 2
    assert classify_mortgage_text("대출 상담 가능") == 0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("융 자 무", 1),
        ("근저당 없음", 1),
        ("대출없음", 1),
        ("근저당 설정", 2),
        ("채권최고액 3억원", 2),
        ("융자 30%", 2),
        ("대출있음", 2),
    ],
)
def test_mortgage_classifier_handles_known_explicit_text_forms(text, expected):
    assert classify_mortgage_text(text) == expected


def test_enrichment_updates_codes_once_and_never_persists_detail_text():
    factory = _session_factory()

    async def detail(article_id: int, complex_id: int):
        return {
            10: {"detailDescription": "융자금 없음"},
            11: {"articleFeatureDescription": "융자 있음"},
            12: {"detailDescription": "특이사항 없음"},
        }[article_id]

    runner = MortgageEnrichmentRunner(factory, detail_fetcher=detail, job_id=9001, concurrency=2)
    assert asyncio.run(runner.run_once(batch_size=3)) == 3
    assert asyncio.run(runner.run_once(batch_size=3)) == 0

    with factory() as session:
        rows = {row.article_id: row for row in session.scalars(select(ListingCurrent)).all()}
        assert {article_id: row.mortgage_code for article_id, row in rows.items()} == {10: 1, 11: 2, 12: 0}
        assert all(row.mortgage_checked_at is not None for row in rows.values())
        assert all("융자" not in (row.description or "") for row in rows.values())
        history = list(session.scalars(select(ListingHistory).order_by(ListingHistory.article_id)).all())
        assert [item.article_id for item in history] == [10, 11]


def test_enrichment_classifies_nested_article_detail_payload():
    factory = _session_factory()

    async def detail(article_id: int, complex_id: int):
        return {"articleDetail": {"detailDescription": "근저당 설정"}}

    runner = MortgageEnrichmentRunner(factory, detail_fetcher=detail, job_id=9003)
    assert asyncio.run(runner.run_once(batch_size=1)) == 1

    with factory() as session:
        assert session.get(ListingCurrent, 10).mortgage_code == 2


def test_enrichment_history_does_not_collide_with_collection_updated_event():
    factory = _session_factory()
    with factory() as session:
        listing = session.get(ListingCurrent, 10)
        session.add(
            ListingHistory(
                article_id=10,
                complex_id=listing.complex_id,
                job_id=9001,
                event_type=HISTORY_UPDATED,
                state_hash=listing.state_hash,
                occurred_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        session.commit()

    async def detail(article_id: int, complex_id: int):
        return {"detailDescription": "융자금 없음"}

    runner = MortgageEnrichmentRunner(factory, detail_fetcher=detail, job_id=9001)
    assert asyncio.run(runner.run_once(batch_size=1)) == 1

    with factory() as session:
        assert session.get(ListingCurrent, 10).mortgage_code == 1
        events = list(session.scalars(select(ListingHistory.event_type).where(ListingHistory.article_id == 10)).all())
        assert sorted(events) == [HISTORY_UPDATED, HISTORY_MORTGAGE_ENRICHED]


def test_run_until_idle_skips_a_failing_pending_article_and_processes_later_rows():
    factory = _session_factory()

    async def detail(article_id: int, complex_id: int):
        if article_id == 10:
            raise RuntimeError("permanent detail failure")
        return {"detailDescription": "융자금 있음"}

    runner = MortgageEnrichmentRunner(factory, detail_fetcher=detail, job_id=9002, concurrency=2)
    assert asyncio.run(runner.run_until_idle(batch_size=1)) == 2

    with factory() as session:
        assert session.get(ListingCurrent, 10).mortgage_checked_at is None
        assert session.get(ListingCurrent, 11).mortgage_checked_at is not None
        assert session.get(ListingCurrent, 12).mortgage_checked_at is not None


def test_article_detail_parser_keeps_only_typed_values_and_rejects_malformed_fields():
    parsed = parse_article_detail(
        {
            "articleDetail": {
                "detailDescription": "융자 없음",
                "roomCount": "3",
                "bathroomCount": 2,
                "parkingPossible": "Y",
                "parkingPerHousehold": "1.25",
                "monthlyManagementCost": "150000",
                "moveInAvailableDate": "2026-08-15",
                "nearestSubwayWalkMinutes": "7",
            }
        }
    )

    assert parsed.mortgage_code == 1
    assert parsed.room_count == 3
    assert parsed.bathroom_count == 2
    assert parsed.parking_possible is True
    assert parsed.parking_per_household_x100 == 125
    assert parsed.monthly_management_cost == 150000
    assert str(parsed.move_in_available_on) == "2026-08-15"
    assert parsed.nearest_subway_walk_minutes == 7
    assert "융자" not in repr(parsed)

    malformed = parse_article_detail(
        {
            "articleDetail": {
                "roomCount": "three",
                "bathroomCount": -1,
                "parkingPossible": "unknown",
                "parkingPerHousehold": "many",
                "monthlyManagementCost": -1,
                "moveInAvailableDate": "not-a-date",
                "nearestSubwayWalkMinutes": "far",
            }
        }
    )
    assert malformed.room_count is None
    assert malformed.bathroom_count is None
    assert malformed.parking_possible is None
    assert malformed.parking_per_household_x100 is None
    assert malformed.monthly_management_cost is None
    assert malformed.move_in_available_on is None
    assert malformed.nearest_subway_walk_minutes is None


def test_article_detail_parser_accepts_site_a_detail_field_spellings():
    parsed = parse_article_detail(
        {
            "articleDetail": {
                "parkingPossibleYN": "Y",
                "moveInPossibleYmd": "20260815",
                "walkingTimeToNearSubway": "7",
            }
        }
    )

    assert parsed.parking_possible is True
    assert str(parsed.move_in_available_on) == "2026-08-15"
    assert parsed.nearest_subway_walk_minutes == 7


def test_combined_enrichment_updates_detail_once_and_retries_transport_failures():
    factory = _session_factory()
    attempts: list[int] = []

    async def detail(article_id: int, complex_id: int):
        attempts.append(article_id)
        if article_id == 10 and attempts.count(article_id) == 1:
            raise RuntimeError("retry later")
        return {
            "articleDetail": {
                "detailDescription": "융자 있음",
                "roomCount": 3,
                "bathroomCount": 2,
                "parkingPossibleYN": "Y",
                "parkingPerHousehold": 1.2,
                "monthlyManagementCost": 180000,
                "moveInPossibleYmd": "20260901",
                "walkingTimeToNearSubway": 4,
            }
        }

    runner = MortgageEnrichmentRunner(factory, detail_fetcher=detail, job_id=9010)
    assert asyncio.run(runner.run_until_idle(batch_size=1)) == 2
    assert asyncio.run(runner.run_until_idle(batch_size=3)) == 1
    assert asyncio.run(runner.run_until_idle(batch_size=3)) == 0

    with factory() as session:
        listing = session.get(ListingCurrent, 10)
        assert listing.detail_checked_at is not None
        assert listing.mortgage_checked_at is not None
        assert listing.room_count == 3
        assert listing.bathroom_count == 2
        assert listing.parking_possible is True
        assert listing.parking_per_household_x100 == 120
        assert listing.monthly_management_cost == 180000
        assert str(listing.move_in_available_on) == "2026-09-01"
        assert listing.nearest_subway_walk_minutes == 4
        events = list(session.scalars(select(ListingHistory.event_type).where(ListingHistory.article_id == 10)).all())
        assert sorted(events) == [HISTORY_MORTGAGE_ENRICHED, HISTORY_DETAIL_ENRICHED]
