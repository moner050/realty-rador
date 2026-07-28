from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from realty_radar.infrastructure.database.models.v2 import UserAccount, UserPreference
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.auth import verify_session_token, SESSION_COOKIE_NAME

router = APIRouter(prefix="/api/user", tags=["user_preference"])


class PreferencePayload(BaseModel):
    favorites: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    loan_profile: Optional[Dict[str, Any]] = None


def get_current_user_account(request: Request, db: Session = Depends(get_db)) -> UserAccount:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")

    user = db.query(UserAccount).filter(UserAccount.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자 정보를 찾을 수 없습니다.")

    return user


@router.get("/preference")
def get_user_preference(
    user: UserAccount = Depends(get_current_user_account),
    db: Session = Depends(get_db),
):
    """로그인 사용자의 저장된 즐겨찾기, 필터, 대출자격 설정을 반환합니다."""
    pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if not pref:
        return {
            "username": user.username,
            "favorites": {"listings": [], "complexes": []},
            "filters": {},
            "loan_profile": {},
        }

    return {
        "username": user.username,
        "favorites": pref.favorites_json or {"listings": [], "complexes": []},
        "filters": pref.filters_json or {},
        "loan_profile": pref.loan_profile_json or {},
    }


@router.post("/preference")
def save_user_preference(
    payload: PreferencePayload,
    user: UserAccount = Depends(get_current_user_account),
    db: Session = Depends(get_db),
):
    """로그인 사용자의 즐겨찾기, 필터, 대출자격 설정을 DB에 보존/동기화합니다."""
    pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if not pref:
        pref = UserPreference(user_id=user.id)
        db.add(pref)

    if payload.favorites is not None:
        pref.favorites_json = payload.favorites
    if payload.filters is not None:
        pref.filters_json = payload.filters
    if payload.loan_profile is not None:
        pref.loan_profile_json = payload.loan_profile

    db.commit()
    return {"status": "ok", "message": "성공적으로 저장되었습니다."}
