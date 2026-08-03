import json
import urllib.parse

from fastapi.testclient import TestClient

from realty_radar.domain.loan.entities import ApplicantProfile
from realty_radar.web.main import app
from realty_radar.web.routes.settings import GUEST_COOKIE_NAME


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


def test_inline_profile_saves_purchase_budget_values_in_guest_cookie():
    response = TestClient(app).post(
        "/settings/inline",
        data={
            "available_cash": "320,000,000",
            "existing_monthly_debt_payment": "450,000",
            "max_monthly_housing_cost": "3,000,000",
            "closing_cost_reserve_percent": "1.75",
        },
    )

    profile = json.loads(urllib.parse.unquote(response.cookies.get(GUEST_COOKIE_NAME)))

    assert response.status_code == 204
    assert profile["available_cash"] == 320_000_000
    assert profile["existing_monthly_debt_payment"] == 450_000
    assert profile["max_monthly_housing_cost"] == 3_000_000
    assert profile["closing_cost_reserve_bps"] == 175
