"""auth.py — Authentication endpoints.

POST /api/v1/auth/login  — exchange username/password for a JWT access token.
POST /api/v1/auth/logout — revoke the current token (server-side jti blocklist).
GET  /api/v1/auth/me     — return current username (token validation check).

Login is rate-limited to 10 attempts per minute per client IP.
"""

import secrets

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.auth.deps import create_access_token, get_current_user, revoke_token
from app.config import settings

router = APIRouter(prefix="/api/v1/auth")

_limiter = Limiter(key_func=get_remote_address)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    username: str


@router.post("/login", response_model=TokenResponse)
@_limiter.limit("10/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> TokenResponse:
    """Verify credentials and return a JWT access token.

    Accepts standard OAuth2 form fields: username and password.
    Rate-limited to 10 requests/minute per IP.
    """
    if not settings.admin_username or not settings.admin_password_hash:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth not configured — set ADMIN_USERNAME and ADMIN_PASSWORD_HASH in .env",
        )

    # Always run bcrypt regardless of username match to prevent timing oracle.
    # Use secrets.compare_digest for the username to avoid string-comparison leaks.
    username_match = secrets.compare_digest(
        form_data.username.encode(), settings.admin_username.encode()
    )
    password_match = bcrypt.checkpw(
        form_data.password.encode(), settings.admin_password_hash.encode()
    )
    if not (username_match and password_match):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": form_data.username})
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=204)
def logout(current_user: str = Depends(get_current_user), request: Request = None) -> None:
    """Revoke the current JWT by adding its jti to the server-side blocklist.

    The token will be rejected on subsequent requests even if it has not expired.
    Note: the blocklist is in-memory and does not survive server restarts.
    """
    auth_header = request.headers.get("Authorization", "") if request else ""
    if auth_header.startswith("Bearer "):
        revoke_token(auth_header[len("Bearer "):])


@router.get("/me", response_model=MeResponse)
def me(current_user: str = Depends(get_current_user)) -> MeResponse:
    """Return the authenticated username. Useful for token validation on page load."""
    return MeResponse(username=current_user)
