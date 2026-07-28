import hmac
import hashlib
import base64
import os
from typing import Optional

from fastapi import Request, HTTPException, Depends, status
from sqlalchemy.orm import Session

from realty_radar.config import settings
from realty_radar.infrastructure.database.models.v2 import UserAccount
from realty_radar.infrastructure.database.session import SessionFactory, get_db

SESSION_COOKIE_NAME = "realty_session"


def hash_password(password: str) -> str:
    """비밀번호를 PBKDF2 HMAC SHA256 해시 문자열로 생성합니다."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return f"{salt.hex()}:${key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """평문 비밀번호와 저장된 해시 문자열의 일치 여부를 검증합니다."""
    try:
        salt_hex, key_hex = hashed_password.split(":$")
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 100000)
        return hmac.compare_digest(key, expected_key)
    except Exception:
        return False


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
        if request.headers.get("HX-Request") == "true":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="로그인이 필요합니다.",
                headers={"HX-Redirect": "/login"},
            )
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )

    return username


def get_current_user_account(request: Request, db: Session = Depends(get_db)) -> UserAccount:
    """현재 로그인된 사용자의 UserAccount 모델을 반환합니다."""
    username = require_authentication(request)
    user = db.query(UserAccount).filter(UserAccount.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자 계정을 찾을 수 없습니다.")
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> UserAccount:
    """관리자(ADMIN) 권한 전용 라우터 보호 의존성."""
    user = get_current_user_account(request, db)
    if user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자(ADMIN) 권한이 필요합니다.",
        )
    return user


def is_admin_user(request: Request, db: Optional[Session] = None) -> bool:
    """현재 사용자가 ADMIN 권한인지 여부를 반환합니다."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_token(token)
    if not username:
        return False
    if db is not None:
        user = db.query(UserAccount).filter(UserAccount.username == username).first()
        return user is not None and user.role == "ADMIN"

    with SessionFactory() as session:
        user = session.query(UserAccount).filter(UserAccount.username == username).first()
        return user is not None and user.role == "ADMIN"


def get_current_username(request: Request) -> str:
    """요청 쿠키에서 유효한 로그인 사용자명을 반환하며, 비로그인 시 'guest_user'를 반환합니다."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_token(token)
    return username if username else "guest_user"
