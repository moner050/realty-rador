import argparse
import asyncio
from realty_radar.application.crawl_pipeline_service import CrawlPipelineService
from realty_radar.infrastructure.database.session import SessionFactory


async def run_crawl_cli(source_code: str, region: str) -> None:
    """수동 크롤링 및 DB 연동 실행 CLI."""
    print(f"[{source_code}] 지역({region}) 수집 파이프라인을 시작합니다...")

    with SessionFactory() as db:
        pipeline = CrawlPipelineService(db)
        result = await pipeline.execute_search_pipeline(source_code, region)

        print("=== 크롤링 파이프라인 수집 완료 ===")
        print(f"대상 소스: {result['source_code']}")
        print(f"지역: {result['region_name']}")
        print(f"수집된 원본 매물: {result['total_fetched']}건")
        print(f"신규 DB 등록: {result['created_count']}건")
        print(f"기존 DB 업데이트: {result['updated_count']}건")


def main():
    parser = argparse.ArgumentParser(description="수동 부동산 매물 크롤링 실행 CLI")
    parser.add_argument("--source", type=str, default="SITE_A", help="사이트 소스 코드 (예: SITE_A)")
    parser.add_argument("--region", type=str, default="여의도동", help="검색 지역명")

    args = parser.parse_args()
    asyncio.run(run_crawl_cli(args.source, args.region))


if __name__ == "__main__":
    main()
