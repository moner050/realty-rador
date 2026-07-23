# Redis 데이터 웜업 및 매물 렌더링 100% 복원 개편 계획서

## 1. 매물 미표시 원인 정밀 분석

1. **Jinja2 템플릿 프로퍼티 복원 누락**:
   - HTML 템플릿(`list_partial.html`)에서 `item.deposit`, `item.monthly_rent`, `item.complex_name`, `item.eligible_loans` 등 템플릿 전용 필드를 참조하는데, Redis 역직렬화(`_dict_to_listing`) 과정에서 기본 `price_deposit`만 수신되어 템플릿 렌더링 시 매물 카드가 빈 값으로 표시되는 현상 발생.

2. **서버 시작 시 Redis 캐시 미적재(Warm-up 필요)**:
   - 서버 구동 시 MySQL 데이터를 Redis로 미리 워밍업 적재하는 서버 시작 이벤트가 없었음.

---

## 2. 해결 방안

### 1) 매물 객체 직렬화/역직렬화 및 프로퍼티 100% 완전 보존
- `_listing_to_dict` 및 `_dict_to_listing`에 `deposit`, `monthly_rent`, `complex_name`, `source_name`, `eligible_loans`(대출 적격 뱃지 리스트)까지 통째로 직렬화하여 적재 및 100% 복원.

### 2) 서버 시작 시 (Lifespan Startup) Redis 자동 데이터 웜업(Warm-up) 구현
- [main.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/main.py)의 Lifespan Startup 이벤트에 MySQL의 기본 매물 조회를 구동하여 서버 구동 즉시 Redis 인메모리로 최신 매물을 초고속 자동 적재.

---

## 3. 검증 계획
- `python -m pytest tests/`로 51개 전체 테스트 정상 통과 검증.
