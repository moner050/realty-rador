# 7단계 다중 사이트 어댑터 확장 및 동일 매물 추정 요약

## 1. 개요
본 문서는 `docs/feature-plan.md` 아키텍처 설계를 바탕으로 **7단계 다중 사이트 어댑터 확장 및 동일 매물 추정**을 구축한 기록 문서입니다.

## 2. 주요 구축 모듈
1. **어댑터 팩토리 및 SITE_B 어댑터 (`src/realty_radar/crawler`)**:
   - `AdapterFactory`: 소스 코드에 따라 `SiteAAdapter` 또는 `SiteBAdapter`를 동적 생성
   - `SiteBParser`, `SiteBNormalizer`, `SiteBAdapter`: 두 번째 사이트 데이터 수집 및 정규화기

2. **동일 매물 추정 서비스 (`src/realty_radar/application/listing_dedup_service.py`)**:
   - `ListingDedupService`: 타 사이트 수집 매물간 가중치 점수 계산 (단지 일치 +40, 거래유형 +10, 면적 ±0.5㎡ +15, 가격 +15, 층 +10, 설명 유사도 +10)
   - 85점 이상: 동일 매물 확정 추정 / 70~84점: 동일 매물 그룹 추정

3. **통합 파이프라인 연동 (`src/realty_radar/application/crawl_pipeline_service.py`)**:
   - 다중 사이트 수집 -> 파싱 -> 정규화 -> 단지 매칭 -> DB 저장 -> 동일 매물 자동 판정

## 3. 검증 결과
- pytest 22개 전체 단위 및 통합 테스트 100% 통과 (22/22 passed)
