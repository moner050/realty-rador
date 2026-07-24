# [Plan] 사용자 개인 설정 영구 보존(Persistence) 고도화 계획

## 1. 개요
기존 메모리 상에서만 일시적으로 유지되던 사용자의 개인 조건 설정(`ApplicantProfile`: 연소득, 순자산, 무주택 여부, 신혼부부, 차용증 목록 등)을 파일 기반 JSON 데이터 영속화(`data/user_profile.json`)로 확장하여, **서버 재시작이나 브라우저 재접속 시에도 저장된 설정값이 100% 지속 유지**되도록 고도화합니다.

---

## 2. 작업 상세 항목

### 1) 프로필 entity DTO 내 직렬화/복원 메서드 추가 (`src/realty_radar/domain/loan/entities.py`)
- `ApplicantProfile.to_dict()`: 프로필 및 하위 `PromissoryNoteEntry` 차용증 항목들을 JSON 직렬화 가능한 dict로 변환.
- `ApplicantProfile.from_dict(data: dict)`: dict 데이터로부터 `ApplicantProfile` 객체 자동 복원.

### 2) 설정 저장소 관리 및 영구 파일 저장/로드 구현 (`src/realty_radar/web/routes/settings.py`)
- 프로필 저장 경로: `data/user_profile.json`
- `load_user_profile()`: 서버 기동 시 및 라우트 호출 시 영구 저장 파일에서 프로필을 안전하게 읽어오는 도구 함수 구현.
- `save_user_profile(profile: ApplicantProfile)`: 설정 저장(`POST /settings`) 시 파일에 즉시 영구 저장.

### 3) 단위 테스트 작성 및 전체 검증
- `tests/unit/test_settings_persistence.py` 추가 및 pytest 검증 실행.
