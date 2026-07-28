import os
import json
import urllib.parse
import urllib.request
from pathlib import Path
from fastapi import APIRouter, Form, Request, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from realty_radar.config import settings
from realty_radar.infrastructure.database.session import get_db
from realty_radar.infrastructure.database.models.v2 import UserAccount
from realty_radar.web.auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    is_authenticated,
    hash_password,
    verify_password,
)

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="src/realty_radar/web/templates")


@router.get("/login", response_class=HTMLResponse, name="login_page")
def login_page(request: Request):
    """로그인 화면 렌더링 (이미 로그인 상태면 메인으로 이동)."""
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

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
    db: Session = Depends(get_db),
):
    """아이디 및 비밀번호 검증 후 세션 쿠키 발급 (DB 계정 및 기본 관리자 계정 지원)."""
    clean_username = username.strip()

    # 1. 관리자 계정 검증
    is_valid = (clean_username == settings.admin_username and password == settings.admin_password)

    # 2. DB 사용자 계정 검증
    if not is_valid:
        user = db.query(UserAccount).filter(UserAccount.username == clean_username).first()
        if user and verify_password(password, user.password_hash):
            is_valid = True

    if is_valid:
        token = create_session_token(clean_username)
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
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


@router.get("/register", response_class=HTMLResponse, name="register_page")
def register_page(request: Request):
    """간소화 회원가입 화면 렌더링."""
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={
            "is_authenticated": False,
            "error": None,
        },
    )


@router.post("/register", response_class=HTMLResponse, name="process_register")
def process_register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    """간소화 회원가입 처리 후 즉시 자동 로그인 세션 생성."""
    clean_username = username.strip()

    if len(clean_username) < 3:
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html",
            context={"is_authenticated": False, "error": "아이디는 최소 3자 이상이어야 합니다."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if len(password) < 4:
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html",
            context={"is_authenticated": False, "error": "비밀번호는 최소 4자 이상이어야 합니다."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if password != password_confirm:
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html",
            context={"is_authenticated": False, "error": "비밀번호 확인이 일치하지 않습니다."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 기존 사용자 중복 확인
    existing_user = db.query(UserAccount).filter(UserAccount.username == clean_username).first()
    if existing_user or clean_username == settings.admin_username:
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html",
            context={"is_authenticated": False, "error": "이미 존재하는 아이디입니다."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 신규 회원 저장
    new_user = UserAccount(
        username=clean_username,
        password_hash=hash_password(password),
    )
    db.add(new_user)
    db.commit()

    # 즉시 자동 로그인 처리
    token = create_session_token(clean_username)
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,
    )
    return response


@router.get("/auth/google/login", name="google_login")
def google_login(request: Request):
    """구글 OAuth 2.0 동의 화면으로 리다이렉트."""
    if not settings.google_client_id or settings.google_client_id.startswith("your_"):
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "is_authenticated": False,
                "error": "Google Client ID가 .env 파일에 설정되지 않았습니다. 관리자 설정을 확인하세요.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "state": "google_oauth_state",
    }
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=google_auth_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/auth/google/callback", name="google_callback")
def google_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """구글 OAuth 2.0 인증 코드 수령 후 토큰 교환 및 자동 계정 생성/로그인."""
    if error or not code:
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "is_authenticated": False,
                "error": f"구글 인증 실패: {error or '인증 코드가 전송되지 않았습니다.'}",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # 1. Authorization Code -> Access Token 교환
        token_url = "https://oauth2.googleapis.com/token"
        token_data = urllib.parse.urlencode({
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        }).encode("utf-8")

        req = urllib.request.Request(token_url, data=token_data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req) as resp:
            token_resp = json.loads(resp.read().decode("utf-8"))

        access_token = token_resp.get("access_token")
        if not access_token:
            raise ValueError("구글 엑세스 토큰을 발급받지 못했습니다.")

        # 2. User Info 조회
        userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        req_user = urllib.request.Request(userinfo_url, headers={"Authorization": f"Bearer {access_token}"})
        with urllib.request.urlopen(req_user) as resp_user:
            user_info = json.loads(resp_user.read().decode("utf-8"))

        google_email = user_info.get("email")
        if not google_email:
            raise ValueError("구글 이메일 정보를 불러올 수 없습니다.")

        username = google_email.strip()

        # 3. DB 사용자 검증 및 자동 회원가입 처리
        user = db.query(UserAccount).filter(UserAccount.username == username).first()
        if not user:
            # 랜덤 패스워드 생성 후 구글 계정 신규 가입
            random_pw = f"google_oauth_{os.urandom(8).hex()}"
            user = UserAccount(
                username=username,
                password_hash=hash_password(random_pw),
            )
            db.add(user)
            db.commit()

        # 4. 세션 토큰 발급 및 로그인 완료
        token = create_session_token(username)
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            max_age=86400 * 7,
        )
        return response

    except Exception as e:
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "is_authenticated": False,
                "error": f"구글 연동 로그인 중 오류 발생: {str(e)}",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )


@router.get("/logout", name="logout")
def logout(request: Request):
    """세션 쿠키 삭제 및 메인 화면으로 리다이렉트."""
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response
