# 상세 검색 조건 모달 UX/UI 개선 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 상세 검색 모달을 점진적 공개 구조로 재배치해 중복된 범위 조작을 줄이고, 필터 의미·URL·저장 조건을 바꾸지 않은 채 더 빠르게 조건을 설정할 수 있게 한다.

**Architecture:** `index.html` 안의 기존 Jinja 슬라이더 매크로와 인라인 모달 제어를 확장한다. 가격·면적은 하나의 예산·면적 표면에 포함하되 기존 hidden input과 `data-range-slider` 계약을 유지하고, 주거·옵션 탭은 기존 input `name`과 `data-quick-preset`을 그대로 둔 채 시각적 그룹과 탭 단위 초기화만 추가한다.

**Tech Stack:** Jinja2, Tailwind utility classes, 바닐라 JavaScript, FastAPI `TestClient`, pytest, agent-browser.

## Global Constraints

- 기존 form `name`, URL 쿼리 값, `ListingSearchFilter` 의미, 저장된 검색 조건을 변경하지 않는다.
- 가격·면적·월세·주거·대출·통근·옵션 필터를 제거하거나 서로 다른 필터로 합치지 않는다.
- 직접 숫자 입력이 기준 조작이고 슬라이더는 보조 조작이다.
- 기존 `data-single-slider`, `data-range-slider`, `data-quick-preset`, `data-monthly-rent-filter`, `data-trade-filter` 계약을 유지한다.
- 기존 HTMX 자동 검색은 유지한다. 탭 초기화와 적용 버튼은 한 번의 `form.requestSubmit()`만 호출해야 한다.
- 라이트/다크 모드에서 보조 문구·테두리·비활성 상태가 읽혀야 하며, 기존 테마 헬퍼 클래스를 재사용한다.
- 모달 내부 외의 필터, Python 파싱, DB 쿼리, API 및 스키마는 변경하지 않는다.
- 테스트는 `python -m pytest`로 실행하고, 기존 사용자의 작업트리 변경과 무관한 파일만 stage한다.

---

## File Structure

- Modify: `src/realty_radar/web/templates/listings/index.html` — 슬라이더의 embedded 배치, 탭별 필터 그룹, 모달 footer와 제어 스크립트.
- Modify: `tests/integration/test_web_v2.py` — 렌더된 상세 필터의 계약, 필터 이름, 그룹, 접근성 마커 회귀.
- Modify: `tests/unit/test_light_theme_templates.py` — 라이트 모드에서 새로운 보조 표면과 텍스트 대비 계약.

### Task 1: 예산·면적과 주거 조건의 점진적 공개

**Files:**
- Modify: `src/realty_radar/web/templates/listings/index.html`
- Modify: `tests/integration/test_web_v2.py`
- Modify: `tests/unit/test_light_theme_templates.py`

**Interfaces:**
- Consumes: 기존 `range_slider`와 `single_slider` 매크로, `min_price_eok`, `max_price_eok`, `filters.*`, `slider_limits`.
- Produces: `data-filter-scope="housing-budget"`, `data-filter-scope="housing-core"`, `data-filter-scope="housing-detail"`로 구획된 동일한 필터 input 집합과 `_render_home_with_memory_db(query: str)` 테스트 helper.

- [ ] **Step 1: 예산·면적과 기본/세부 주거 그룹의 실패하는 렌더링 테스트를 작성한다.**

`tests/integration/test_web_v2.py`에 기존 `TestClient`/SQLite fixture 패턴을 재사용해 다음 테스트를 추가한다.

```python
def _render_home_with_memory_db(query: str):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        return TestClient(app).get(query)
    finally:
        app.dependency_overrides.clear()


def test_detailed_filter_groups_budget_and_progressive_housing_controls():
    response = _render_home_with_memory_db("/?trade_types=SALE&min_price_eok=2&max_price_eok=6&min_households=500")

    assert response.status_code == 200
    assert 'data-filter-scope="housing-budget"' in response.text
    assert 'data-filter-scope="housing-core"' in response.text
    assert 'data-filter-scope="housing-detail"' in response.text
    assert 'data-slider-name="min_price_eok"' in response.text
    assert 'data-slider-name="max_price_eok"' in response.text
    assert 'data-slider-name="min_exclusive_area"' in response.text
    assert 'data-slider-name="max_exclusive_area"' in response.text
    assert 'name="min_construction_year"' in response.text
    assert 'name="max_subway_walk_minutes"' in response.text
    assert 'data-slider-variant="embedded"' in response.text
```

`tests/unit/test_light_theme_templates.py`에는 embedded 표면이 어두운 텍스트/테두리를 사용하는지 확인한다.

```python
def test_embedded_filter_surface_keeps_light_theme_contrast():
    listings = (TEMPLATE_ROOT / "listings" / "index.html").read_text(encoding="utf-8")

    assert 'data-slider-variant="embedded"' in listings
    assert 'text-slate-900 dark:text-slate-100' in listings
    assert 'border-slate-200 dark:border-slate-800' in listings
```

- [ ] **Step 2: 실패를 확인한다.**

Run: `python -m pytest tests/integration/test_web_v2.py -k "detailed_filter_groups" tests/unit/test_light_theme_templates.py -k "embedded_filter" -q`

Expected: `data-filter-scope`와 `data-slider-variant="embedded"`가 없어 실패한다.

- [ ] **Step 3: 슬라이더 매크로에 embedded 변형을 추가하고 주거 탭을 재배치한다.**

`range_slider`와 `single_slider`에 선택적 `variant='card'` 매개변수를 추가한다. 매크로 최상위 요소는 기존 `data-*` 속성을 유지하고, embedded일 때만 별도 카드 그림자/테두리를 제거한다.

```jinja2
{% macro range_slider(key, min_id, min_name, min_value, max_id, max_name, max_value, minimum, maximum, step, label, unit, helper='', variant='card') -%}
<div data-range-slider="{{ key }}" data-unit="{{ unit }}"
     {% if variant == 'embedded' %}data-slider-variant="embedded"{% endif %}
     class="{% if variant == 'embedded' %}border-t border-slate-200 dark:border-slate-800 pt-4 text-slate-900 dark:text-slate-100{% else %}rounded-xl border border-slate-300/80 dark:border-slate-700/70 bg-white dark:bg-slate-950/60 p-4 shadow-sm text-slate-900 dark:text-slate-100{% endif %}">
```

`single_slider`도 같은 `variant` 매개변수와 마커를 사용한다.

```jinja2
{% macro single_slider(id, name, value, minimum, maximum, step, label, unit, scale=1, helper='', variant='card') -%}
<div data-single-slider data-scale="{{ scale }}" data-unit="{{ unit }}"
     {% if variant == 'embedded' %}data-slider-variant="embedded"{% endif %}
     class="{% if variant == 'embedded' %}border-t border-slate-200 dark:border-slate-800 pt-4 text-slate-900 dark:text-slate-100{% else %}rounded-xl border border-slate-300/80 dark:border-slate-700/70 bg-white dark:bg-slate-950/60 p-3.5 shadow-sm text-slate-900 dark:text-slate-100{% endif %}">
```

주거 탭에서 기존 `transaction-advanced-filters` 내부를 다음 구조로 바꾼다.

```jinja2
<section data-filter-scope="housing-budget" class="theme-subtle-surface rounded-xl border p-4 space-y-4">
  <div><h2>예산·면적</h2><p>직접 입력으로 범위를 정하고, 필요할 때 슬라이더로 조정하세요.</p></div>
  {{ range_slider('price', 'min-price-eok', 'min_price_eok', min_price_eok, 'max-price-eok', 'max_price_eok', max_price_eok, 0, slider_limits.price_eok, 0.1, '가격·보증금', '억', variant='embedded') }}
  {{ range_slider('exclusive-area', 'min-exclusive-area', 'min_exclusive_area', filters.min_exclusive_area, 'max-exclusive-area', 'max_exclusive_area', filters.max_exclusive_area, 0, slider_limits.area, 1, '전용면적', '㎡', '59㎡는 약 18평, 84㎡는 약 25평입니다.', variant='embedded') }}
  <div data-monthly-rent-filter>{{ single_slider('max-monthly-rent', 'max_monthly_rent', filters.max_monthly_rent, 0, slider_limits.monthly_rent_manwon, 5, '월세 상한', '만원', 10000, '월세 매물에만 적용됩니다.', variant='embedded') }}</div>
</section>
<section data-filter-scope="housing-core" class="space-y-3">
  <h2>기본 주거 조건</h2>
  <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
    {{ single_slider('min-construction-year', 'min_construction_year', filters.min_construction_year, 1960, slider_limits.construction_year, 1, '준공연도 최소', '년', variant='embedded') }}
    {{ single_slider('min-households', 'min_households', filters.min_households, 0, slider_limits.households, 100, '세대수 최소', '세대', variant='embedded') }}
    {{ single_slider('min-room-count', 'min_room_count', filters.min_room_count, 0, 10, 1, '방 최소', '개', variant='embedded') }}
    {{ single_slider('min-bathroom-count', 'min_bathroom_count', filters.min_bathroom_count, 0, 10, 1, '욕실 최소', '개', variant='embedded') }}
  </div>
</section>
<details data-filter-scope="housing-detail" id="advanced-housing-conditions" class="theme-subtle-surface rounded-xl border p-4">
  <summary>세부 주거 조건</summary>
  <div class="grid grid-cols-1 gap-3 pt-3 sm:grid-cols-2">
    {{ single_slider('min-parking-per-household', 'min_parking_per_household', filters.min_parking_per_household, 0, slider_limits.parking, 0.1, '세대당 주차 최소', '대', variant='embedded') }}
    {{ single_slider('max-monthly-management-cost', 'max_monthly_management_cost', filters.max_monthly_management_cost, 0, slider_limits.management_cost_manwon, 1, '관리비 상한', '만원', 10000, variant='embedded') }}
    {{ single_slider('max-subway-walk-minutes', 'max_subway_walk_minutes', filters.max_subway_walk_minutes, 0, slider_limits.subway_minutes, 1, '역 도보 상한', '분', variant='embedded') }}
    {{ single_slider('recent-days', 'recent_days', filters.recent_days, 1, slider_limits.recent_days, 1, '최근 등록', '일', variant='embedded') }}
  </div>
</details>
```

준공연도·세대수·방·욕실은 `housing-core` 안에 두고, 주차·관리비·역 도보·최근 등록은 `housing-detail` 안에 둔다. 기존 `name`, `id`, slider key, hidden input, helper 문구, `updateTradeFilters()`의 월세 토글은 바꾸지 않는다.

- [ ] **Step 4: 렌더링과 라이트 테마 테스트를 통과시킨다.**

Run: `python -m pytest tests/integration/test_web_v2.py -k "detailed_filter_groups or trade_specific_filters" tests/unit/test_light_theme_templates.py -q`

Expected: PASS. 가격·면적·월세·주거 필터 이름과 기존 거래 유형 동적 표시 계약이 유지된다.

- [ ] **Step 5: Task 1 파일만 커밋한다.**

```powershell
git add -- src/realty_radar/web/templates/listings/index.html tests/integration/test_web_v2.py tests/unit/test_light_theme_templates.py
git commit -m "feat: organize detailed housing filters"
```

### Task 2: 프리셋·옵션 그룹화와 탭 단위 모달 조작

**Files:**
- Modify: `src/realty_radar/web/templates/listings/index.html`
- Modify: `tests/integration/test_web_v2.py`

**Interfaces:**
- Consumes: 기존 `data-quick-preset`, checkbox `name`/`value`, `form`, `detailedFilterModal`, `.filter-tab-btn`, `.filter-tab-content`.
- Consumes from Task 1: `_render_home_with_memory_db(query: str)`.
- Produces: `data-filter-scope` 기반 탭 초기화와 `data-detailed-filter-count`/`data-clear-filter-tab` footer 제어.

- [ ] **Step 1: 프리셋/옵션 그룹 및 footer 제어의 실패하는 렌더링 테스트를 작성한다.**

```python
def test_detailed_filter_modal_groups_presets_options_and_tab_actions():
    response = _render_home_with_memory_db("/?direct_trade_only=true&only_eligible_loans=true")

    assert response.status_code == 200
    assert 'data-preset-group="recommended"' in response.text
    assert 'data-preset-group="loan-only"' in response.text
    assert 'data-option-group="listing"' in response.text
    assert 'data-option-group="convenience"' in response.text
    assert 'data-option-group="financing"' in response.text
    assert 'data-detailed-filter-count' in response.text
    assert 'data-clear-filter-tab' in response.text
    assert 'name="direct_trade_only" value="true"' in response.text
    assert 'name="only_eligible_loans" value="true"' in response.text
    assert 'name="only_purchase_affordable" value="true"' in response.text
    assert 'data-quick-preset="combo-didimdol-town"' in response.text
    assert 'data-quick-preset="loan-didimdol"' in response.text
```

- [ ] **Step 2: 실패를 확인한다.**

Run: `python -m pytest tests/integration/test_web_v2.py -k "groups_presets_options" -q`

Expected: 새로운 그룹/하단 제어 마커가 없어 실패한다.

- [ ] **Step 3: 프리셋·옵션 마크업과 모달 제어를 구현한다.**

프리셋의 기존 버튼/속성은 유지하고 그룹 컨테이너만 추가한다.

```jinja2
<section data-preset-group="recommended" class="rounded-xl border border-indigo-200 dark:border-indigo-900/60 bg-indigo-50/80 dark:bg-slate-950 p-3.5 space-y-2">
  <h4>추천 조합</h4>
  <p>대출 기준과 선호 주거 조건을 함께 적용합니다.</p>
  <div class="flex flex-wrap gap-2">기존 combo-didimdol-town, combo-bogeum-town, combo-newborn-town, combo-newborn-jeonse-town 버튼을 원래 속성으로 이동한다.</div>
</section>
<section data-preset-group="loan-only" class="space-y-2">
  <h4>대출 조건만</h4>
  <p>예산과 면적 기준만 빠르게 설정합니다.</p>
  <div class="flex flex-wrap gap-2">기존 loan-didimdol, loan-bogeum, loan-newborn-buy, loan-butimmok, loan-newborn-rent, tidy-town 버튼을 원래 속성으로 이동한다.</div>
</section>
```

옵션은 기존 checkbox를 각각 한 번만 포함한 채 세 `fieldset`으로 재배치한다. `exclude_short_term`의 hidden `false` input 및 숨겨진 `move_in_by` input은 유지한다.

```jinja2
<fieldset data-option-group="listing"><legend>거래·매물 형태</legend><p>direct_trade_only, exclude_short_term, exclude_first_floor, group_by_complex checkbox를 기존 name/value로 이동한다.</p></fieldset>
<fieldset data-option-group="convenience"><legend>주거 편의</legend><p>parking_possible_only checkbox를 기존 name/value로 이동한다.</p></fieldset>
<fieldset data-option-group="financing">
  <legend>자금 조건</legend>
  <p>대출·구매 가능 매물은 개인 자격 정보에 따라 달라집니다.</p>
  <p>safe_lessor_hug_only, only_eligible_loans, only_purchase_affordable checkbox를 기존 name/value로 이동한다.</p>
</fieldset>
```

모달 footer에 카운트, 탭 초기화, 적용/닫기 버튼을 둔다.

```jinja2
<div class="sticky bottom-0 border-t border-slate-200 bg-white pt-3 dark:border-slate-800 dark:bg-slate-900">
  <output data-detailed-filter-count aria-live="polite"></output>
  <button type="button" data-clear-filter-tab>이 탭 초기화</button>
  <button type="button" data-apply-detailed-filter>적용 및 닫기</button>
</div>
```

인라인 script에서 다음 순서를 구현한다.

1. `setActiveFilterTab(target)`은 탭의 `aria-selected`, `tabindex`, 활성 클래스와 콘텐츠의 `hidden`을 함께 갱신한다.
2. `updateDetailedFilterCount()`는 활성 탭 안의 checked checkbox와 값이 있는 hidden slider input을 `Set`으로 세어 `현재 N개 조건 적용`을 출력한다. `exclude_short_term=false`, `page_size`, 그리고 disabled input은 세지 않는다.
3. 기존 single/range clear 이벤트의 값 갱신 부분을 `clearSingleSlider(container, submit)`/`clearRangeSlider(container, submit)` 내부 함수로 추출한다. 기존 개별 초기화는 `submit=true`을 유지한다.
4. `data-clear-filter-tab` 클릭은 현재 visible `.filter-tab-content` 안의 slider/checkbox/select만 초기화하고, `form.requestSubmit()`을 한 번 호출한다. 다른 탭 및 상단 거래 유형은 유지한다.
5. `data-apply-detailed-filter` 클릭은 `form.requestSubmit()`을 한 번 호출한 뒤 `detailedFilterModal.close()`한다.

각 탭 전환 및 form `change`/`input` 후 `updateDetailedFilterCount()`를 호출한다. `data-quick-preset`과 통근 버튼의 기존 동작은 바꾸지 않는다.

- [ ] **Step 4: 마크업 계약 테스트를 통과시킨다.**

Run: `python -m pytest tests/integration/test_web_v2.py -k "groups_presets_options or detailed_filter_groups" -q`

Expected: PASS. 모든 기존 checkbox/프리셋 속성과 새 그룹/footer 마커가 함께 렌더된다.

- [ ] **Step 5: Task 2 파일만 커밋한다.**

```powershell
git add -- src/realty_radar/web/templates/listings/index.html tests/integration/test_web_v2.py
git commit -m "feat: streamline detailed filter modal controls"
```

### Task 3: 동작·시각 회귀 검증

**Files:**
- Modify: Task 1 또는 Task 2의 파일만, 직접 검증 실패를 재현하는 테스트가 먼저 추가된 경우에 한함.

**Interfaces:**
- Consumes: 완성된 상세 필터 모달, 기존 `hx-sync="this:replace"` 검색 form, 브라우저의 `dialog`/input 이벤트.
- Produces: 검색 의미를 보존한 모달 조작 검증 결과.

- [ ] **Step 1: 자동화된 전체 회귀를 실행한다.**

Run: `python -m pytest -q; node --test tests/web/test_listing_map_controller.mjs`

Expected: 전체 Python 및 지도 컨트롤 테스트가 통과한다.

- [ ] **Step 2: 로컬 브라우저로 라이트·다크 모달을 확인한다.**

작업트리의 앱을 임시 로컬 포트에서 실행한 뒤 다음을 확인한다.

1. 상세 필터를 열면 예산·면적이 하나의 표면에 있고 직접 입력이 먼저 보인다.
2. 기본 주거 조건은 즉시 보이고 세부 주거 조건은 접혀 있다.
3. 월세 거래 선택/해제에 따라 월세 상한이 표시/비활성 전환된다.
4. 프리셋과 옵션이 설계된 목적별 그룹으로 보이고, 탭 초기화는 활성 탭만 비운다.
5. 적용/닫기는 한 번의 검색 갱신과 모달 닫힘을 만들며, URL의 기존 필터 값은 유지된다.
6. 라이트·다크 모드에서 보조 텍스트와 footer가 읽히고, 작은 viewport에서 footer 버튼에 접근할 수 있다.

기존 data/API를 사용하며, 외부 SITE_A/NAVER 호출은 실행하지 않는다. 브라우저와 임시 서버는 검증 뒤 종료한다.

- [ ] **Step 3: 직접 검증 실패만 최소 수정하고 다시 테스트한다.**

실패가 발견되면 먼저 그 실패를 재현하는 `test_web_v2.py` 또는 `test_light_theme_templates.py` 테스트를 추가한다. 그 다음 `index.html`만 최소 수정하고 Step 1과 Step 2를 다시 실행한다.

- [ ] **Step 4: 검증 수정이 있을 때만 별도 커밋한다.**

```powershell
git add -- src/realty_radar/web/templates/listings/index.html tests/integration/test_web_v2.py tests/unit/test_light_theme_templates.py
git commit -m "test: verify detailed filter modal ux"
```

## 계획 자체 검토

- 설계의 예산·면적, 주거 계층, 프리셋/옵션 그룹, 모달 footer 요구사항은 각각 Task 1 또는 Task 2에 매핑했다.
- `name`, hidden input, preset 속성, HTMX 자동 검색을 보존하는 조건을 모든 Task의 상위 제약으로 고정했다.
- 탭 초기화의 단일 제출 동작은 슬라이더 clear 함수 추출과 명시적 `form.requestSubmit()`으로 구현 경계를 정했다.
- 파일/테스트/명령/커밋 범위에 미완성 지시나 placeholder가 없다.
