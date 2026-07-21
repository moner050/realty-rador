from typing import Annotated
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from realty_radar.domain.loan.entities import ApplicantProfile

router = APIRouter(prefix="/settings", tags=["settings"])
templates = Jinja2Templates(directory="src/realty_radar/web/templates")

# 메모리 상의 세션 사용자 프로필 기본 설정
session_user_profile = ApplicantProfile()


@router.get("", response_class=HTMLResponse, name="settings_index")
def get_settings(request: Request):
    """사용자 조건 설정 화면."""
    return templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={"profile": session_user_profile},
    )


@router.post("", response_class=HTMLResponse, name="update_settings")
def update_settings(
    request: Request,
    is_homeless: Annotated[bool, Form()] = False,
    annual_income: Annotated[int, Form()] = 60000000,
    net_assets: Annotated[int, Form()] = 300000000,
    is_newlywed: Annotated[bool, Form()] = False,
    is_first_home_buyer: Annotated[bool, Form()] = False,
    child_count: Annotated[int, Form()] = 0,
):
    """개인 자격 조건 설정 저장."""
    global session_user_profile
    session_user_profile = ApplicantProfile(
        is_homeless=is_homeless,
        annual_income=annual_income,
        net_assets=net_assets,
        is_newlywed=is_newlywed,
        is_first_home_buyer=is_first_home_buyer,
        child_count=child_count,
    )

    return templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={
            "profile": session_user_profile,
            "success_message": "개인 자격 조건이 성공적으로 저장되었습니다.",
        },
    )
