# 수집 데이터 HTML 엔티티 특수문자(&amp; -> &) 정제 해결 계획서

## 1. 개요 및 원인
네이버부동산 수집 데이터의 단지명 및 주소에 포함된 엠퍼샌드(`&`) 등의 특수문자가 HTML 엔티티(`&amp;`) 형태로 수집 및 DB에 저장되어 UI 화면에 그대로 노출되는 현상을 해결합니다.

---

## 2. 해결 방안

### 1) 수집 정규화 시 `html.unescape` 적용
- **[normalizer.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/crawler/adapters/site_a/normalizer.py)**:
  - `complex_name_raw`, `address_raw`, `description_raw` 정규화 시 `html.unescape()`를 호출하여 `&amp;` -> `&`, `&lt;` -> `<`, `&gt;` -> `>` 등 깨끗한 원래 특수문자로 복원.

### 2) 기존 DB 오염 데이터 일괄 정제
- 기존 DB에 `&amp;` 형태로 저장된 매물명/주소 데이터를 Direct SQL `REPLACE(complex_name_raw, '&amp;', '&')` 로 일괄 수복.

---

## 3. 검증 계획
1. DB 내 `&amp;` 수복 마이그레이션 실행 및 변경 확인.
2. pytest 테스트 구동 및 100% 통과 확인.
