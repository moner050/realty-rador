import hmac
import hashlib
import base64
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse

from realty_radar.config import settings

SESSION_COOKIE_NAME = "realty_session"


def create_session_token(username: str) -> str:
    """사용자명으로 서명된 세션 토큰을 생성합니다."""
    signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        username.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    raw = f"{username}:{signature}"
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


def verify_session_token(token: str | None) -> str | None:
    """세션 토큰을 검증하고 유효하면 username을 반환합니다."""
    if not token:
        return None
    try:
        decoded = base64.b64decode(token.encode("utf-8")).decode("utf-8")
        if ":" not in decoded:
            return None
        username, signature = decoded.split(":", 1)
        expected_signature = hmac.new(
            settings.secret_key.encode("utf-8"),
            username.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if hmac.compare_digest(signature, expected_signature):
            return username
    except Exception:
        return None
    return None


def is_authenticated(request: Request) -> bool:
    """요청의 쿠키를 통해 현재 사용자가 로그인 상태인지 검증합니다."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_token(token)
    return username is not None


def require_authentication(request: Request) -> str:
    """로그인 필수 라우터 보호 의존성 (비로그인 시 /login으로 303 리다이렉트 예외)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_token(token)

    if not username:
        # HTMX 비동기 요청일 경우 HTMX 전용 리다이렉트 헤더 전송 지원
        if request.headers.get("HX-Request") == "true":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="로그인이 필요합니다.",
                headers={"HX-Redirect": "/login"},
            )
        # 일반 HTTP GET/POST 요청 시 /login으로 리다이렉트
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )

    return username


def get_current_username(request: Request) -> str:
    """요청 쿠키에서 유효한 로그인 사용자명을 반환하며, 비로그인 시 'guest_user'를 반환합니다."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_token(token)
    return username if username else "guest_user"
