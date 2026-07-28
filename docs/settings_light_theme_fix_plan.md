# 개인 자격 및 정책대출 조건 설정 모달 화이트(라이트) 테마 가독성 개선 계획서

## 1. 개요
개인 자격 및 정책대출 조건 설정 모달 (`_inline_profile_modal.html`)의 "인원별 차용 지원 가능 금액 지정" 카드를 포함한 모달 내부 텍스트, 입력 박스, 차용인 카드 항목들이 하드코딩된 다크 테마 전용 클래스(`text-indigo-200`, `bg-slate-900`, `bg-slate-950`, `text-white` 등)로 작성되어 있어, 화이트(라이트) 테마 환경에서 바탕색과 글자색 대비 부족으로 가독성이 현저히 저하됩니다.

## 2. 주요 개선 내용

### 1) 인원별 차용 지원 가능 금액 지정 패널
- **패널 컨테이너**: `border-indigo-200 dark:border-indigo-900/50 bg-indigo-50/80 dark:bg-indigo-950/20`
- **제목 텍스트**: `text-indigo-950 dark:text-indigo-200 font-bold`
- **아이콘**: `text-indigo-600 dark:text-indigo-400`
- **설명 텍스트**: `text-slate-600 dark:text-slate-400`

### 2) 동적 차용인 카드 (JavaScript 동적 생성 DOM)
- **카드 컨테이너**: `border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 shadow-sm`
- **인원 라벨**: `text-slate-800 dark:text-slate-300 font-semibold`
- **차용인 이름 입력란**: `border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white`
- **지원 가능 금액 라벨**: `text-slate-600 dark:text-slate-400`
- **지원 가능 금액 입력란**: `border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white`

### 3) 모달 본문 & 폼 요소 라이트/다크 테마 적용
- **모달 컨테이너**: `border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 shadow-2xl`
- **체크박스 카드 라벨/도움말**:
  - 배경 및 테두리: `border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950/60`
  - 항목명: `text-slate-900 dark:text-white`
  - 도움말: `text-slate-600 dark:text-slate-400`
- **Input 박스 (자녀 수, 연소득, 순자산, 차용증 인원 수)**: `border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white`
- **차용증 총 금액**: `border-indigo-200 dark:border-slate-800 bg-indigo-50/50 dark:bg-slate-900/80 text-indigo-900 dark:text-indigo-300 font-extrabold`

## 3. 대상 파일
- `src/realty_radar/web/templates/settings/_inline_profile_modal.html`

## 4. 검증 계획
- pytest 단위/통합 테스트 실행하여 템플릿 구문 및 로직 정상 검증
- 라이트 테마 및 다크 테마 전환 환경에서 개인 자격 설정 모달 가독성 검증
