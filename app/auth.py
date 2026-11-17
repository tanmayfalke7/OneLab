"""JWT authentication with header and cookie transports."""
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from fastapi import HTTPException, Request, status
from .config import get_settings

settings = get_settings()
# Hash once when the app starts; checkpw does constant-time comparison internally.
DEMO_PASSWORD_HASH = bcrypt.hashpw(settings.demo_user_password.encode(), bcrypt.gensalt())

def verify_demo_credentials(email: str, password: str) -> bool:
    return email == settings.demo_user_email and bcrypt.checkpw(password.encode(), DEMO_PASSWORD_HASH)

def create_access_token(email: str) -> str:
    now = datetime.now(timezone.utc)
    claims = {"sub": email, "role": "auditor", "iat": now, "exp": now + timedelta(minutes=settings.access_token_expire_minutes)}
    return jwt.encode(claims, settings.secret_key, algorithm=settings.jwt_algorithm)

def _token_from_request(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "): return authorization.removeprefix("Bearer ").strip()
    return request.cookies.get("access_token")

async def get_current_user(request: Request) -> dict:
    token = _token_from_request(request)
    if not token: raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        if claims.get("role") != "auditor" or not claims.get("sub"): raise jwt.InvalidTokenError("invalid claims")
        return claims
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired access token") from exc
