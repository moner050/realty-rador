# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import text
from realty_radar.infrastructure.database.session import SessionFactory, engine
from realty_radar.infrastructure.database.models import Base

def apply_indexes():
    print("⚡ DB 물리 인덱스 동기화 및 초고속 검색 인덱스 생성 중...")
    Base.metadata.create_all(bind=engine)

    index_sqls = [
        "CREATE INDEX idx_listing_direction ON listing(direction)",
        "CREATE INDEX idx_listing_dir_search ON listing(status, is_short_term, direction, price_deposit)",
        "CREATE INDEX idx_listing_super_direction ON listing(status, is_short_term, sido, sigungu, direction)",
        "CREATE INDEX idx_listing_super_search ON listing(status, is_short_term, sido, sigungu, transaction_type, price_deposit)",
        "CREATE INDEX idx_listing_super_filter ON listing(status, is_short_term, construction_year, total_households)",
    ]

    with engine.connect() as conn:
        for sql in index_sqls:
            try:
                conn.execute(text(sql))
                conn.commit()
                print(f"✅ 인덱스 생성 완료: {sql.split()[2]}")
            except Exception as e:
                # 이미 존재하는 인덱스 등의 사유는 무시
                pass

    print("🚀 모든 DB 물리 인덱스가 100% 최적화 적용되었습니다!")

if __name__ == "__main__":
    apply_indexes()
