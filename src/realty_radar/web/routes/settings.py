import json
import logging
import re
import urllib.parse
from typing import Annotated
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from realty_radar.config import settings
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.domain.loan.entities import ApplicantProfile, PromissoryNoteEntry
from realty_radar.web.auth import SESSION_COOKIE_NAME, is_authenticated, verify_session_token
from realty_radar.web.jinja_filters import register_jinja_filters

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])
templates = Jinja2Templates(directory="src/realty_radar/web/templates")
register_jinja_filters(templates)

PROFILES_DIR = settings.data_directory / "user_profiles"
GUEST_COOKIE_NAME = "realty_guest_profile"


def get_profile_file_path(username: str = "guest_user"):
    """사용자별 격리된 프로필 파일 경로 반환."""
    clean_user = re.sub(r"[^a-zA-Z0-9_-]", "_", username.strip()) if username else "guest_user"
    return PROFILES_DIR / f"{clean_user}.json"


def get_filter_file_path(username: str = "guest_user"):
    """사용자별 격리된 검색 필터 파일 경로 반환."""
    clean_user = re.sub(r"[^a-zA-Z0-9_-]", "_", username.strip()) if username else "guest_user"
    return PROFILES_DIR / f"{clean_user}_filter.json"


def load_user_profile(username: str = "guest_user") -> ApplicantProfile:
    """사용자 계정별 격리된 파일에서 프로필 로드."""
    try:
        file_path = get_profile_file_path(username)
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return ApplicantProfile.from_dict(data)
    except Exception as e:
        logger.warning("[%s] 사용자 프로필 파일 로드 실패(기본값 사용): %s", username, e)
    return ApplicantProfile()


def save_user_profile(profile: ApplicantProfile, username: str = "guest_user") -> None:
    """사용자 계정별 격리된 파일에 프로필 영구 저장."""
    try:
        file_path = get_profile_file_path(username)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("[%s] 사용자 프로필 영구 저장 중 오류: %s", username, e)


def load_user_search_filter(username: str) -> ListingSearchFilter | None:
    """로그인 사용자 계정별 격리된 파일에서 검색 필터 로드."""
    try:
        if not username:
            return None
        file_path = get_filter_file_path(username)
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return ListingSearchFilter.from_dict(data)
    except Exception as e:
        logger.warning("[%s] 사용자 검색 필터 파일 로드 실패: %s", username, e)
    return None


def save_user_search_filter(filter_params: ListingSearchFilter, username: str) -> None:
    """로그인 사용자 계정별 파일에 검색 필터 저장."""
    try:
        if not username:
            return
        file_path = get_filter_file_path(username)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(filter_params.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("[%s] 사용자 검색 필터 파일 저장 중 오류: %s", username, e)


def get_request_user_profile(request: Request) -> ApplicantProfile:
    """요청자 상태(로그인 사용자 ➔ 파일, 비로그인 ➔ 게스트 쿠키)에 맞는 프로필 반환."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_token(token)

    if username:
        return load_user_profile(username)

    # 비로그인 사용자인 경우 게스트 쿠키 탐색
    guest_cookie = request.cookies.get(GUEST_COOKIE_NAME)
    if guest_cookie:
        try:
            raw_json = urllib.parse.unquote(guest_cookie)
            data = json.loads(raw_json)
            return ApplicantProfile.from_dict(data)
        except Exception as e:
            logger.warning("게스트 쿠키 프로필 파싱 실패: %s", e)

    return ApplicantProfile()


@router.get("", response_class=HTMLResponse, name="settings_index")
def get_settings(request: Request):
    """사용자 조건 설정 화면 (로그인/비로그인 하이브리드 프로필 로드)."""
    user_profile = get_request_user_profile(request)
    return templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={"profile": user_profile, "is_authenticated": is_authenticated(request)},
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
    """개인 자격 조건 설정 저장 (로그인 ➔ 서버파일 / 비로그인 ➔ 쿠키 & 로컬스토리지)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_token(token)

    # 동적 차용증 목록 구성
    note_entries: list[PromissoryNoteEntry] = []
    if use_promissory_note:
        for name, amt_str in zip(promissory_note_names, promissory_note_amounts):
            clean_amt = int(re.sub(r"[^0-9]", "", str(amt_str))) if amt_str else 0
            if name.strip() or clean_amt > 0:
                note_entries.append(PromissoryNoteEntry(name=name.strip(), amount=clean_amt))

    user_profile = ApplicantProfile(
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

    response = templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={
            "profile": user_profile,
            "success_message": "개인 자격 조건이 성공적으로 저장되었습니다.",
            "is_authenticated": is_authenticated(request),
        },
    )

    if username:
        # 로그인 사용자는 서버 파일에 저장
        save_user_profile(user_profile, username=username)
    else:
        # 비로그인 사용자는 guest_profile 쿠키(30일 유지) 설정
        profile_json = json.dumps(user_profile.to_dict(), ensure_ascii=False)
        quoted_json = urllib.parse.quote(profile_json)
        response.set_cookie(
            key=GUEST_COOKIE_NAME,
            value=quoted_json,
            max_age=86400 * 30,
            httponly=False,
            samesite="lax",
        )

    return response
