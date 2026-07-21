# 8단계 대출 규칙 및 정부 정책대출 예상 평가 엔진 구축 요약

## 1. 개요
본 문서는 `docs/feature-plan.md` 아키텍처 설계를 바탕으로 **8단계 대출 규칙 및 정부 정책대출 예상 평가 엔진**을 구축한 기록 문서입니다.

## 2. 주요 구축 모듈
1. **정부 대출 평가 도메인 (`src/realty_radar/domain/loan`)**:
   - `ApplicantProfile`: 사용자 신청 자격 프로필 (부부합산 소득, 순자산, 무주택 세대주 여부, 신혼부부, 생애최초, 자녀 수)
   - `LoanRuleEvaluator`: 디딤돌 대출(매매가 5억/6억 이하, 전용 85㎡ 이하) 및 버팀목 전세자금 대출 조건 산출 엔진

2. **정책 대출 로더 & 비즈니스 서비스 (`src/realty_radar/enrichment/loan` & `application`)**:
   - `LoanPolicyLoader`: 시행일 기반 규칙 버전 로더
   - `LoanEvaluationService`: 매물 ID 기반 2단계 적격성 상태(`ELIGIBLE`, `PROPERTY_ELIGIBLE`, `INELIGIBLE`) 종합 평가

3. **개인 자격 조건 설정 Web UI (`src/realty_radar/web`)**:
   - `routes/settings.py`: GET/POST `/settings`
   - `templates/settings/index.html`: 개인 소득, 자산, 주택소유 및 혼인 상태 등록 UI

## 3. 검증 결과
- `python -m pytest` 실행 결과 28개 전체 단위 및 통합 테스트 100% 통과 (28/28 passed)
