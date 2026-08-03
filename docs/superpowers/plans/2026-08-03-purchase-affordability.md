# 실구매 가능성 계산 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 매매 매물의 예상 필요 현금과 월 총주거비를 계산하고, 사용자의 두 한도를 동시에 만족하는 매물만 검색할 수 있게 한다.

**Architecture:** ApplicantProfile에 구매 자금·월 한도만 추가하고, PurchaseAffordabilityService가 정책대출 평가 결과와 매물 상세를 순수 계산한다. 목록의 일반/그룹 커서 검색은 SQL에서 넓은 매매 후보를 keyset으로 읽고 애플리케이션에서 정확한 구매 가능성만 판정하므로, hot query에는 조인이나 계산식이 추가되지 않는다.

**Tech Stack:** Python 3.10, FastAPI/Jinja2/HTMX, SQLAlchemy, dataclasses, SQLite integration tests, MySQL benchmark contract.

## Global Constraints

- 매매(SALE)만 이 기능의 계산·필터 대상이며, 전세·월세의 기존 정책대출 동작은 변경하지 않는다.
- ApplicantProfile.net_assets는 정책대출 자격용 순자산으로 유지한다. 구매투입 현금은 available_cash로 분리한다.
- 선택 대출은 현재 정책대출 평가의 ELIGIBLE/PROPERTY_ELIGIBLE 결과만 사용한다. 은행 DSR·신용·담보 심사와 법정 세금·중개보수 계산은 구현하지 않는다.
- 부대비용은 closing_cost_reserve_bps(기본 200, 2.00%)의 사용자 조정 가능한 예비비이며 법정 비용으로 표기하지 않는다.
- 원리금은 30년(360개월) 원리금균등, 원 단위 ROUND_HALF_UP으로 계산한다.
- 매물 hot query는 JOIN·COUNT·OFFSET 없이 유지한다. 구매 가능 필터는 매매가 상한을 가진 keyset 후보 스캔 후 Python에서 최종 판정한다.
- 커서 filter fingerprint와 applicant fingerprint를 보존한다. 일반, 그룹, 이전 페이지, only_eligible_loans 조합에서 중복·누락이 없어야 한다.
- 개인 조건은 settings/_inline_profile_modal.html과 /settings/inline만 사용한다. 독립 /settings 화면을 만들지 않는다.
- 누락된 보유 현금 또는 월 한도에서는 구매 가능 여부를 단정하지 않으며, 필터 요청은 결과를 넓히지 않고 명시적 설정 오류로 응답한다.
- 모든 자동 검증은 python -m pytest로 실행한다.

---

### Task 1: 구매 가능성 프로필 값의 저장·복원

**Files:**
- Modify: src/realty_radar/domain/loan/entities.py
- Modify: src/realty_radar/web/routes/settings.py
- Modify: src/realty_radar/web/templates/settings/_inline_profile_modal.html
- Create: tests/unit/test_applicant_profile_affordability.py
- Modify: tests/integration/test_web_v2.py

**Interfaces:**
- Produces ApplicantProfile.available_cash: int | None, existing_monthly_debt_payment: int, max_monthly_housing_cost: int | None, closing_cost_reserve_bps: int.
- ApplicantProfile.to_dict and from_dict round-trip all four values while old profile JSON still loads with None, 0, None, and 200.
- POST /settings/inline accepts blank optional money inputs and persists them for both guest and logged-in paths.

- [x] **Step 1: Write failing profile serialisation tests**

~~~python
def test_purchase_affordability_profile_values_round_trip():
    profile = ApplicantProfile(
        available_cash=320_000_000,
        existing_monthly_debt_payment=450_000,
        max_monthly_housing_cost=3_000_000,
        closing_cost_reserve_bps=175,
    )

    assert ApplicantProfile.from_dict(profile.to_dict()) == profile


def test_legacy_profile_gets_safe_affordability_defaults():
    profile = ApplicantProfile.from_dict({"annual_income": 60_000_000, "net_assets": 300_000_000})

    assert profile.available_cash is None
    assert profile.existing_monthly_debt_payment == 0
    assert profile.max_monthly_housing_cost is None
    assert profile.closing_cost_reserve_bps == 200
~~~

- [x] **Step 2: Run test to verify it fails**

Run: python -m pytest tests/unit/test_applicant_profile_affordability.py -q

Expected: FAIL because ApplicantProfile does not accept available_cash.

- [x] **Step 3: Write the minimal profile and form implementation**

~~~python
@dataclass
class ApplicantProfile:
    # Existing policy-loan fields remain unchanged.
    available_cash: int | None = None
    existing_monthly_debt_payment: int = 0
    max_monthly_housing_cost: int | None = None
    closing_cost_reserve_bps: int = 200
~~~

~~~python
def _optional_money(raw: str | None) -> int | None:
    digits = re.sub(r"[^0-9]", "", raw or "")
    return int(digits) if digits else None


def _reserve_percent_to_bps(raw: str | None) -> int:
    cleaned = re.sub(r"[^0-9.]", "", raw or "")
    try:
        percent = Decimal(cleaned)
    except InvalidOperation:
        return 200
    return min(1_000, max(0, int((percent * 100).quantize(Decimal("1")))))
~~~

Add the four values to to_dict/from_dict. Accept the four new form values as strings in update_inline_settings, parse blank money fields with _optional_money, and keep existing_monthly_debt_payment at 0 when blank. Parse the UI percentage with _reserve_percent_to_bps, render profile.closing_cost_reserve_bps / 100 with step="0.01", and bound the input to 0.00–10.00%. In the inline profile modal add fields labelled 구매 투입 가능 현금, 기존 월 대출상환액, 감당 가능한 월 총주거비, and 부대비용 예비비율(%). Retain 순자산 unchanged for policy eligibility.

- [x] **Step 4: Add route and template contracts**

~~~python
def test_inline_profile_form_exposes_purchase_budget_inputs():
    template = Path("src/realty_radar/web/templates/settings/_inline_profile_modal.html").read_text(encoding="utf-8")

    assert 'name="available_cash"' in template
    assert 'name="existing_monthly_debt_payment"' in template
    assert 'name="max_monthly_housing_cost"' in template
    assert 'name="closing_cost_reserve_bps"' in template


def test_update_inline_settings_keeps_blank_purchase_limits_optional(client):
    response = client.post("/settings/inline", data={"available_cash": "", "max_monthly_housing_cost": ""})

    assert response.status_code == 204
~~~

- [x] **Step 5: Run tests and commit**

Run: python -m pytest tests/unit/test_applicant_profile_affordability.py tests/integration/test_web_v2.py -q

Expected: PASS.

~~~powershell
git add src/realty_radar/domain/loan/entities.py src/realty_radar/web/routes/settings.py src/realty_radar/web/templates/settings/_inline_profile_modal.html tests/unit/test_applicant_profile_affordability.py tests/integration/test_web_v2.py
git commit -m "feat: save purchase affordability profile"
~~~

### Task 2: 순수 실구매 가능성 계산기

**Files:**
- Create: src/realty_radar/application/purchase_affordability_service.py
- Create: tests/unit/test_purchase_affordability_service.py

**Interfaces:**
- Produces PurchaseAffordabilityResult with selected loan, reserve, required cash, monthly principal-and-interest, management cost, existing debt, total monthly cost, and three nullable affordability flags.
- Produces PurchaseAffordabilityService.calculate(listing, evaluations, applicant) -> PurchaseAffordabilityResult | None.
- Only a sale listing with a positive primary_price produces a result.

- [x] **Step 1: Write failing calculator tests**

~~~python
def sale_listing(*, price: int, management_cost: int | None = None):
    return SimpleNamespace(trade_type=1, primary_price=price, monthly_management_cost=management_cost)


def eligible(product_code: str, amount: int, rate: float):
    return LoanEvaluationResult(
        product_code=product_code,
        product_name=product_code,
        status=LoanEligibilityStatus.ELIGIBLE,
        max_loan_amount=amount,
        interest_rate=rate,
    )


def test_calculator_uses_largest_eligible_loan_then_lower_rate_for_ties():
    result = PurchaseAffordabilityService().calculate(
        sale_listing(price=600_000_000, management_cost=180_000),
        [eligible("DIDIMDOL", 360_000_000, 2.65), eligible("BOGUMJARI", 360_000_000, 3.95)],
        ApplicantProfile(
            available_cash=300_000_000,
            existing_monthly_debt_payment=200_000,
            max_monthly_housing_cost=2_000_000,
            closing_cost_reserve_bps=200,
        ),
    )

    assert result.selected_loan.product_code == "DIDIMDOL"
    assert result.closing_cost_reserve == 12_000_000
    assert result.required_cash == 252_000_000
    assert result.monthly_principal_and_interest == 1_450_670
    assert result.total_monthly_housing_cost == 1_830_670
    assert result.cash_budget_met is True
    assert result.monthly_budget_met is True
    assert result.is_affordable is True


def test_calculator_returns_indeterminate_affordability_for_missing_limits():
    result = PurchaseAffordabilityService().calculate(sale_listing(price=500_000_000), [], ApplicantProfile())

    assert result.required_cash == 510_000_000
    assert result.monthly_principal_and_interest == 0
    assert result.cash_budget_met is None
    assert result.monthly_budget_met is None
    assert result.is_affordable is None


def test_zero_interest_loan_is_split_evenly_over_360_months():
    result = PurchaseAffordabilityService().calculate(
        sale_listing(price=120_000_000), [eligible("ZERO", 120_000_000, 0)], ApplicantProfile()
    )

    assert result.monthly_principal_and_interest == 333_333
~~~

- [x] **Step 2: Run test to verify it fails**

Run: python -m pytest tests/unit/test_purchase_affordability_service.py -q

Expected: FAIL with ModuleNotFoundError for purchase_affordability_service.

- [x] **Step 3: Write the minimal calculation implementation**

~~~python
@dataclass(frozen=True, slots=True)
class PurchaseAffordabilityResult:
    selected_loan: LoanEvaluationResult | None
    closing_cost_reserve: int
    required_cash: int
    monthly_principal_and_interest: int
    monthly_management_cost: int
    existing_monthly_debt_payment: int
    total_monthly_housing_cost: int
    cash_budget_met: bool | None
    monthly_budget_met: bool | None
    is_affordable: bool | None
~~~

~~~python
def _monthly_payment(principal: int, annual_rate: float, term_months: int = 360) -> int:
    if principal <= 0:
        return 0
    monthly_rate = Decimal(str(annual_rate)) / Decimal("1200")
    if monthly_rate == 0:
        return int((Decimal(principal) / term_months).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    factor = (Decimal(1) + monthly_rate) ** term_months
    payment = Decimal(principal) * monthly_rate * factor / (factor - Decimal(1))
    return int(payment.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
~~~

Choose from evaluation.is_eligible, positive max_loan_amount, and non-null interest_rate, ordered by (-max_loan_amount, interest_rate, product_code). Calculate ceil(price * closing_cost_reserve_bps / 10000), max(0, price - loan) + reserve, and principal + actual management cost (or 0) + existing debt. Set is_affordable only when both component flags are non-null. Return None for non-sale or invalid-price input.

- [x] **Step 4: Run tests and commit**

Run: python -m pytest tests/unit/test_purchase_affordability_service.py -q

Expected: PASS.

~~~powershell
git add src/realty_radar/application/purchase_affordability_service.py tests/unit/test_purchase_affordability_service.py
git commit -m "feat: calculate purchase affordability"
~~~

### Task 3: Cursor-safe 구매 가능 매물 검색

**Files:**
- Modify: src/realty_radar/domain/listing/filters.py
- Modify: src/realty_radar/application/listing_search_service.py
- Modify: tests/integration/test_listing_search_v2.py
- Modify: tests/integration/test_web_v2.py

**Interfaces:**
- Produces ListingSearchFilter.only_purchase_affordable: bool and includes it in fingerprint_values, to_dict, and from_dict.
- ListingSearchService.search_listings and search_complex_listings return only sale listings that have PurchaseAffordabilityResult.is_affordable is True when the flag is set.
- A flagged request without both available_cash and max_monthly_housing_cost raises ListingSearchValidationError("purchase affordability profile incomplete") before any listing query.

- [x] **Step 1: Write failing filter and cursor tests**

~~~python
def test_purchase_affordable_filter_scans_to_the_first_matching_page_without_duplicates():
    session = _session_with_sale_prices(500_000_000, 600_000_000, 700_000_000)
    applicant = ApplicantProfile(available_cash=300_000_000, max_monthly_housing_cost=2_000_000)
    filters = ListingSearchFilter(only_purchase_affordable=True, page_size=1, sort_by="price_asc")

    first = ListingSearchService(session, cursor_secret="test-secret").search_listings(filters, applicant)
    second = ListingSearchService(session, cursor_secret="test-secret").search_listings(
        ListingSearchFilter(only_purchase_affordable=True, page_size=1, sort_by="price_asc", cursor=first.next_cursor),
        applicant,
    )

    assert [row.article_id for row in first.items + second.items] == [2001, 2002]


def test_purchase_affordable_filter_rejects_incomplete_profile_before_select(monkeypatch):
    service = ListingSearchService(_session(), cursor_secret="test-secret")
    monkeypatch.setattr(service, "_scalars", lambda _statement: pytest.fail("must not query listings"))

    with pytest.raises(ListingSearchValidationError, match="profile incomplete"):
        service.search_listings(
            ListingSearchFilter(only_purchase_affordable=True), ApplicantProfile(available_cash=300_000_000)
        )


def test_purchase_filter_changes_filter_fingerprint():
    normal = ListingSearchFilter(page_size=1)
    affordable = ListingSearchFilter(page_size=1, only_purchase_affordable=True)

    assert normal.fingerprint_values() != affordable.fingerprint_values()
~~~

- [x] **Step 2: Run test to verify it fails**

Run: python -m pytest tests/integration/test_listing_search_v2.py tests/integration/test_web_v2.py -q

Expected: FAIL because ListingSearchFilter does not accept only_purchase_affordable.

- [x] **Step 3: Add filter parsing and pre-SQL validation**

~~~python
@dataclass(slots=True)
class ListingSearchFilter:
    # Existing fields remain in their current order.
    only_purchase_affordable: bool = False
~~~

~~~python
def _validate_purchase_affordability_profile(self, filters: ListingSearchFilter, applicant: ApplicantProfile | None) -> None:
    if not filters.only_purchase_affordable:
        return
    if applicant is None or applicant.available_cash is None or applicant.max_monthly_housing_cost is None:
        raise ListingSearchValidationError("purchase affordability profile incomplete")
~~~

Call the helper in _run_search immediately after _validate(filters) and before _search_rows or _search_grouped. Add only_purchase_affordable to parse_search_filter and to _filter_query_items.

- [x] **Step 4: Implement the bounded keyset candidate scan**

~~~python
MAX_SUPPORTED_PURCHASE_LOAN = 420_000_000


def _purchase_candidate_rows(self, filters, applicant):
    sale_filters = replace(
        filters,
        trade_type=1,
        trade_types=[1],
        only_purchase_affordable=False,
        only_eligible_loans=False,
    )
    return self._filtered_rows(sale_filters).where(
        ListingCurrent.primary_price <= applicant.available_cash + MAX_SUPPORTED_PURCHASE_LOAN
    )
~~~

Add _purchase_affordability_for_listing that reuses attached loan_evaluations when present, otherwise evaluates the four existing policy products, then calls PurchaseAffordabilityService.calculate. Add the shared runtime predicate:

~~~python
def _matches_runtime_filters(self, listing, filters, applicant) -> bool:
    is_loan_eligible = self._is_loan_eligible(listing, applicant)
    if filters.only_eligible_loans and not is_loan_eligible:
        return False
    if not filters.only_purchase_affordable:
        return True
    calculation = self._purchase_affordability_for_listing(listing, applicant)
    listing.purchase_affordability = calculation
    return calculation is not None and calculation.is_affordable is True
~~~

Route both the existing eligible scans and new purchase-affordability scans through a shared keyset loop that reads page_size + 1 qualifying candidates. For the new filter use _purchase_candidate_rows; for existing eligible-only search retain _eligible_candidate_rows. Do not fetch all matching rows or use OFFSET.

- [x] **Step 5: Preserve grouped ranking and previous-page behavior**

Use _matches_runtime_filters when each grouped complex’s candidate listings are materialized. A group is eligible only if by_complex[complex_id] contains at least one purchase-affordable listing. Keep the existing scan_anchor, _raw_bound_is_safe, sort-key ranking, and next/previous cursor encoding unchanged.

~~~python
def test_grouped_purchase_filter_returns_only_complexes_with_a_qualifying_sale():
    result = ListingSearchService(_seed_grouped_session()).search_listings(
        ListingSearchFilter(group_by_complex=True, only_purchase_affordable=True, page_size=10),
        ApplicantProfile(available_cash=300_000_000, max_monthly_housing_cost=2_000_000),
    )

    assert [group.complex_id for group in result.grouped_items] == [1001]


def test_purchase_filter_combines_with_policy_loan_filter():
    result = ListingSearchService(_session()).search_listings(
        ListingSearchFilter(only_purchase_affordable=True, only_eligible_loans=True),
        ApplicantProfile(available_cash=300_000_000, max_monthly_housing_cost=2_000_000),
    )

    assert all(any(loan.is_eligible for loan in row.loan_evaluations) for row in result.items)
~~~

- [x] **Step 6: Run tests and commit**

Run: python -m pytest tests/integration/test_listing_search_v2.py tests/integration/test_web_v2.py tests/unit/test_home_loan_enrichment.py -q

Expected: PASS, including existing cursor and policy-loan tests.

~~~powershell
git add src/realty_radar/domain/listing/filters.py src/realty_radar/application/listing_search_service.py tests/integration/test_listing_search_v2.py tests/integration/test_web_v2.py
git commit -m "feat: filter purchase-affordable listings"
~~~

### Task 4: 카드·HTMX 오류 화면에 구매 가능성 표시

**Files:**
- Modify: src/realty_radar/web/routes/home.py
- Modify: src/realty_radar/web/templates/listings/index.html
- Modify: src/realty_radar/web/templates/listings/_listing_cards.html
- Modify: src/realty_radar/web/templates/listings/list_partial.html
- Modify: src/realty_radar/web/templates/listings/search_error.html
- Modify: tests/unit/test_home_loan_enrichment.py
- Create: tests/integration/test_purchase_affordability_ui.py

**Interfaces:**
- _enrich_listings_with_loans attaches item.purchase_affordability to each valid sale item after policy evaluation, while preserving evaluations calculated during a filtered scan.
- parse_search_filter accepts only_purchase_affordable=true; _filter_query_items and pagination preserve it.
- A profile-incomplete filter response provides search_error_reason == "purchase_profile_incomplete" and a settings-linking message for both full and HTMX results.

- [x] **Step 1: Write failing route and template tests**

~~~python
def test_result_card_shows_affordability_breakdown_and_disclaimer(client):
    response = client.get("/?only_purchase_affordable=false")

    assert response.status_code == 200
    assert "예상 필요 현금" in response.text
    assert "월 총주거비" in response.text
    assert "정책대출 기준 예상치" in response.text


def test_htmx_purchase_filter_without_limits_returns_settings_error(client):
    response = client.get("/listings/search?only_purchase_affordable=true", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "#search-results"
    assert "구매 투입 가능 현금과 월 총주거비를 먼저 설정" in response.text


def test_affordability_query_round_trips_through_pagination():
    filters = parse_search_filter(only_purchase_affordable=True)

    assert ("only_purchase_affordable", "true") in _filter_query_items(filters)
~~~

- [x] **Step 2: Run test to verify it fails**

Run: python -m pytest tests/unit/test_home_loan_enrichment.py tests/integration/test_purchase_affordability_ui.py tests/integration/test_web_v2.py -q

Expected: FAIL because the route does not parse or render purchase affordability.

- [x] **Step 3: Enrich visible sale listings without re-evaluating cached policy results**

~~~python
def _enrich_listings_with_affordability(result, applicant) -> None:
    service = PurchaseAffordabilityService()
    for item in _listing_items(result):
        evaluations = getattr(item, "loan_evaluations", [])
        calculation = service.calculate(item, evaluations, applicant)
        if calculation is not None:
            item.purchase_affordability = calculation
~~~

Call it after _enrich_listings_with_loans. Do not replace a non-empty item.loan_evaluations; the existing unit test must continue to prove cached scan results are reused.

- [x] **Step 4: Add the filter control, card block, and explicit error reason**

~~~html
<label class="flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-slate-300">
  <input type="checkbox" name="only_purchase_affordable" value="true" {% if filters.only_purchase_affordable %}checked{% endif %}>
  <span>실구매 가능 매물만</span>
</label>
~~~

~~~html
{% if item.purchase_affordability is defined %}
<section data-purchase-affordability class="mt-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-xs text-slate-800 dark:border-indigo-900/60 dark:bg-indigo-950/20 dark:text-slate-200">
  <p class="font-bold">예상 필요 현금 {{ item.purchase_affordability.required_cash | korean_money }}</p>
  <p>월 원리금 + 관리비 + 기존 대출 = 월 총주거비 {{ item.purchase_affordability.total_monthly_housing_cost | korean_money }}</p>
  <p class="mt-1 text-slate-600 dark:text-slate-400">정책대출 기준 예상치이며 실제 대출·세금·중개보수는 계약 전 확인하세요.</p>
</section>
{% endif %}
~~~

Extend _render_search_error with a reason argument. Catch ListingSearchValidationError by its message and render the purchase-profile message only for that condition; retain the generic invalid-filter error for all existing validation failures.

- [x] **Step 5: Run UI regressions and commit**

Run: python -m pytest tests/unit/test_home_loan_enrichment.py tests/integration/test_purchase_affordability_ui.py tests/integration/test_web_v2.py tests/integration/test_listing_detail_ui.py -q

Expected: PASS.

~~~powershell
git add src/realty_radar/web/routes/home.py src/realty_radar/web/templates/listings/index.html src/realty_radar/web/templates/listings/_listing_cards.html src/realty_radar/web/templates/listings/list_partial.html src/realty_radar/web/templates/listings/search_error.html tests/unit/test_home_loan_enrichment.py tests/integration/test_purchase_affordability_ui.py
git commit -m "feat: show purchase affordability on listings"
~~~

### Task 5: 회귀·성능 검증과 운영 안내

**Files:**
- Modify: README.md
- Modify: tests/unit/test_benchmark_listing_search.py
- Modify: docs/superpowers/specs/2026-08-03-purchase-affordability-design.md only if implementation exposed a documented contract mismatch

**Interfaces:**
- README states the four inputs, the 2% default planning reserve, the 30-year policy-loan estimate, and its non-approval disclaimer.
- The benchmark contract explicitly runs normal, grouped, eligible-loans, and a purchase-affordable mode with exact marker/cardinality checks when a MySQL dataset is available.

- [x] **Step 1: Write failing benchmark mode contract test**

~~~python
def test_purchase_affordability_benchmark_mode_has_a_distinct_route_marker():
    mode = _mode_specs(complex_id=None)["purchase-affordable"]

    assert "only_purchase_affordable=true" in mode.path
    assert mode.mode_marker == b'data-search-mode="purchase-affordable"'
    assert mode.expected_items == 20
~~~

- [x] **Step 2: Run test to verify it fails**

Run: python -m pytest tests/unit/test_benchmark_listing_search.py -q

Expected: FAIL because purchase-affordable is not a benchmark mode.

- [x] **Step 3: Add a deterministic benchmark profile and documentation**

Add purchase-affordable to MODE_NAMES and _mode_specs, with a stable test-only profile cookie or an explicit in-process profile fixture accepted by the benchmark client. Its route must include only_purchase_affordable=true, page_size=20, and the marker data-search-mode="purchase-affordable". Keep the 500,000 active-listing preflight, HTTP 2xx, exact 20-item, and p95 checks; do not mark an unavailable MySQL connection as a pass.

Add this README paragraph:

~~~text
실구매 가능성은 구매 투입 가능 현금, 기존 월 대출상환액, 감당 가능한 월 총주거비, 부대비용 예비비율(기본 2%)을 사용합니다. 정책대출 기준으로 30년 원리금균등을 계산한 계획용 예상치이며, 은행 심사와 취득세·중개보수의 법정 계산을 대체하지 않습니다.
~~~

- [x] **Step 4: Run complete verification and commit**

Run: python -m pytest -q

Run: python scripts/benchmark_listing_search.py --mode normal --mode grouped --mode eligible-loans --mode purchase-affordable

Run when MySQL is available: EXPLAIN ANALYZE for the normal and purchase-affordable price-ordered candidate statements; record the selected index and p95. If the local MySQL listener is absent, report the benchmark as unavailable rather than passing it.

~~~powershell
git add README.md tests/unit/test_benchmark_listing_search.py docs/superpowers/specs/2026-08-03-purchase-affordability-design.md
git commit -m "docs: verify purchase affordability search"
~~~
