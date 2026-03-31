"""auth.py — Authentication endpoints.

POST /api/v1/auth/login  — exchange username/password for a JWT access token.
POST /api/v1/auth/logout — client-side token removal; server just confirms.
GET  /api/v1/auth/me     — return current username (token validation check).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel

from app.auth.deps import create_access_token, get_current_user
from app.config import settings

router = APIRouter(prefix="/api/v1/auth")

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    username: str


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    """Verify credentials and return a JWT access token.

    Accepts standard OAuth2 form fields: username and password.
    """
    if not settings.admin_username or not settings.admin_password_hash:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth not configured — set ADMIN_USERNAME and ADMIN_PASSWORD_HASH in .env",
        )
    username_match = form_data.username == settings.admin_username
    password_match = _pwd_context.verify(form_data.password, settings.admin_password_hash)
    if not (username_match and password_match):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": form_data.username})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(current_user: str = Depends(get_current_user)) -> MeResponse:
    """Return the authenticated username. Useful for token validation on page load."""
    return MeResponse(username=current_user)
