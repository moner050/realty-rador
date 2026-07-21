# 4단계 단지 정보 결합 및 매칭 엔진 구축 요약

## 1. 개요
본 문서는 `docs/feature-plan.md` 아키텍처 설계를 바탕으로 **4단계 단지 정보 결합 및 매칭 엔진**을 구축한 기록 문서입니다.

## 2. 주요 구축 모듈
1. **단지명 정규화 & 매칭 점수 엔진 (`src/realty_radar/domain/complex`)**:
   - `normalize_complex_name`: 괄호, 동/차수/단지 키워드 및 특수문자 제거 정규화
   - `ComplexMatchEngine`: 주소 완전일치(+100점), 정규화 단지명 완전일치(+95점), `RapidFuzz` 텍스트 유사도 산출

2. **단지 매칭 비즈니스 서비스 (`src/realty_radar/application/complex_match_service.py`)**:
   - `ComplexMatchService`: 수집 매물의 단지 자동 매칭, `complex_alias` 별칭 생성/업데이트, 미매칭 단지의 신규 `apartment_complex` 자동 등록

3. **단지 상세 Web UI (`src/realty_radar/web`)**:
   - GET `/complexes/{complex_id}` 라우터 및 `templates/complexes/detail.html` (준공연도, 세대수, 최고 층수, 주차대수 카드 뷰 및 해당 단지 매물 목록)
   - POST `/complexes/match` (수동 매칭 연결 API)

## 3. 검증 결과
- `python -m pytest` 실행 결과 16개 전체 단위 및 통합 테스트 100% 통과 (16/16 passed)
