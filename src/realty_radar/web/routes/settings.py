import re
from typing import Annotated
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from realty_radar.domain.loan.entities import ApplicantProfile, PromissoryNoteEntry
from realty_radar.web.jinja_filters import register_jinja_filters

router = APIRouter(prefix="/settings", tags=["settings"])
templates = Jinja2Templates(directory="src/realty_radar/web/templates")
register_jinja_filters(templates)

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
    has_newborn: Annotated[bool, Form()] = False,
    is_first_home_buyer: Annotated[bool, Form()] = False,
    child_count: Annotated[int, Form()] = 0,
    use_promissory_note: Annotated[bool, Form()] = False,
    promissory_note_person_count: Annotated[int, Form()] = 0,
    promissory_note_amount: Annotated[int, Form()] = 0,
    promissory_note_names: Annotated[list[str], Form()] = [],
    promissory_note_amounts: Annotated[list[str], Form()] = [],
):
    """개인 자격 조건 설정 저장."""
    global session_user_profile

    # 동적 차용증 목록 구성
    note_entries: list[PromissoryNoteEntry] = []
    if use_promissory_note:
        for name, amt_str in zip(promissory_note_names, promissory_note_amounts):
            clean_amt = int(re.sub(r"[^0-9]", "", str(amt_str))) if amt_str else 0
            if name.strip() or clean_amt > 0:
                note_entries.append(PromissoryNoteEntry(name=name.strip(), amount=clean_amt))

    session_user_profile = ApplicantProfile(
        is_homeless=is_homeless,
        annual_income=annual_income,
        net_assets=net_assets,
        is_newlywed=is_newlywed,
        has_newborn=has_newborn,
        is_first_home_buyer=is_first_home_buyer,
        child_count=child_count,
        use_promissory_note=use_promissory_note,
        promissory_note_person_count=promissory_note_person_count,
        promissory_note_amount=promissory_note_amount,
        promissory_notes=note_entries,
    )

    return templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={
            "profile": session_user_profile,
            "success_message": "개인 자격 조건이 성공적으로 저장되었습니다.",
        },
    )
