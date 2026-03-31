"""auth/deps.py — JWT creation and FastAPI auth dependencies.

Two variants:
  get_current_user   — raises 401 if no valid token (use on protected endpoints)
  get_optional_user  — returns None if no valid token (use on public endpoints that
                       return different data when authenticated)

When settings.auth_disabled is True (local dev), both dependencies return "dev"
immediately with no token check.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def create_access_token(data: dict) -> str:
    """Sign and return a JWT access token.

    Args:
        data: Payload to encode. Typically {"sub": username}.

    Returns:
        Signed JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> str:
    """Require a valid JWT. Raises 401 if missing or invalid.

    Returns the username from the token payload.
    Dev bypass: if settings.auth_disabled is True, returns "dev" unconditionally.
    """
    if settings.auth_disabled:
        return "dev"

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exc
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc
    return username


def get_optional_user(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[str]:
    """Return username if a valid JWT is present, otherwise None.

    Never raises — callers use the returned value to decide what to expose.
    Dev bypass: if settings.auth_disabled is True, returns "dev" unconditionally.
    """
    if settings.auth_disabled:
        return "dev"

    if token is None:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        username: str | None = payload.get("sub")
        return username
    except JWTError:
        return None
