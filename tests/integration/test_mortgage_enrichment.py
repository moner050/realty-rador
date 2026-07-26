import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.mortgage_enrichment_service import MortgageEnrichmentRunner, classify_mortgage_text
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
