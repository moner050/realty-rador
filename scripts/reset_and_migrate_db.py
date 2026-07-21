import sys
from pathlib import Path

# 루트 디렉토리를 파이썬 모듈 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import text
from realty_radar.infrastructure.database.models import Base, CrawlSource
from realty_radar.infrastructure.database.session import SessionFactory, engine


def reset_and_recreate_database():
    """DB 전체 드롭 후 한글 코멘트 스키마로 완전히 재구축."""
    print("=" * 60)
    print("Realty Radar MySQL 데이터베이스 전체 초기화 및 재생성 시작...")
    print("=" * 60)

    # 1. 외래키 제약조건 비활성화 후 기존 테이블 삭제
    with engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
        
        tables = [
            "listing_history",
            "listing",
            "complex_alias",
            "apartment_complex",
            "crawl_job",
            "crawl_schedule",
            "crawl_source",
            "alembic_version",
        ]
        for tbl in tables:
            conn.execute(text(f"DROP TABLE IF EXISTS `{tbl}`;"))
            print(f"-> 테이블 드롭 완료: {tbl}")

        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
        conn.commit()

    # 2. ORM 모델 메타데이터 기반 모든 테이블 및 한글 Comment 포함 생성
    Base.metadata.create_all(engine)
    print("\n[성공] 모든 테이블 및 한글 컬럼 주석(Comment) 재생성 완료!")

    # 3. 기본 크롤링 출처 사이트 시드 데이터 삽입
    with SessionFactory() as db:
        site_a = CrawlSource(
            source_code="SITE_A",
            source_name="네이버부동산 (Site A)",
            base_url="https://land.naver.com",
            rate_limit_ms=2000,
            is_active=True,
        )
        site_b = CrawlSource(
            source_code="SITE_B",
            source_name="아실/직방 (Site B)",
            base_url="https://site-b.com",
            rate_limit_ms=2000,
            is_active=True,
        )
        db.add(site_a)
        db.add(site_b)
        db.commit()
        print("[성공] 기본 수집 출처 시드 데이터 (SITE_A, SITE_B) 삽입 완료!")

    print("\n데이터베이스 전체 초기화 및 한글 주석 적용이 완벽하게 완료되었습니다!")


if __name__ == "__main__":
    reset_and_recreate_database()
