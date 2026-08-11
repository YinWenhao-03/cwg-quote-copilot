from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    algorithm, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
    if algorithm != "pbkdf2_sha256":
        return False
    salt = base64.b64decode(salt_b64)
    expected = base64.b64decode(digest_b64)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
    return hmac.compare_digest(actual, expected)


def create_access_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user.id,
        "role": user.role,
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.app_secret, algorithm="HS256")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    try:
        payload = jwt.decode(
            credentials.credentials,
            get_settings().app_secret,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效") from exc
    user = db.scalar(select(User).where(User.id == payload.get("sub"), User.active.is_(True)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权执行此操作")
        return user

    return dependency
