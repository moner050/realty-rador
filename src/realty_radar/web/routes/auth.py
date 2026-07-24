from pathlib import Path
from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from realty_radar.config import settings
from realty_radar.web.auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    is_authenticated,
)

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="src/realty_radar/web/templates")


@router.get("/login", response_class=HTMLResponse, name="login_page")
def login_page(request: Request):
    """로그인 화면 렌더링 (이미 로그인 상태면 /jobs로 이동)."""
    if is_authenticated(request):
        return RedirectResponse(url="/jobs", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={
            "is_authenticated": False,
            "error": None,
        },
    )


@router.post("/login", response_class=HTMLResponse, name="process_login")
def process_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """아이디 및 비밀번호 검증 후 세션 쿠키 발급."""
    if username.strip() == settings.admin_username and password == settings.admin_password:
        token = create_session_token(username.strip())
        response = RedirectResponse(url="/jobs", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            max_age=86400 * 7,  # 7일 유효
        )
        return response

    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={
            "is_authenticated": False,
            "error": "아이디 또는 비밀번호가 올바르지 않습니다.",
        },
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@router.get("/logout", name="logout")
def logout(request: Request):
    """세션 쿠키 삭제 및 메인 화면으로 리다이렉트."""
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response
