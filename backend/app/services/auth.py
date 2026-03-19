"""Supabase JWT verification and current user resolution."""
from typing import Optional
from datetime import datetime, timedelta

from fastapi import Request
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from passlib.context import CryptContext

from app.db.models.user import User

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Dev user id when DEV_AUTH_BYPASS is True
DEV_USER_ID = "dev-user"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a plain password."""
    return pwd_context.hash(password)


def _get_bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:].strip()
    return request.query_params.get("token")


async def get_current_user_from_request(
    request: Request, session: AsyncSession
) -> Optional[User]:
    """
    Extract Bearer token, verify Supabase JWT (or dev bypass), create/update user in DB, return User.
    """
    settings = get_settings()
    token = _get_bearer_token(request)

    # Dev bypass: no token or invalid token -> use dev user
    if settings.dev_auth_bypass:
        if not token:
            return await _get_or_create_dev_user(session)
        try:
            _decode_jwt(token, settings)
        except (JWTError, Exception):
            return await _get_or_create_dev_user(session)

    if not token:
        return None

    try:
        payload = _decode_jwt(token, settings)
    except JWTError:
        return None

    sub = payload.get("sub")
    if not sub:
        return None
    email = payload.get("email") or ""
    name = None
    if "user_metadata" in payload and isinstance(payload["user_metadata"], dict):
        name = payload["user_metadata"].get("name")

    # Upsert user
    result = await session.execute(select(User).where(User.id == sub))
    user = result.scalar_one_or_none()
    if user:
        user.email = email
        if name is not None:
            user.name = name
        await session.commit()
        await session.refresh(user)
    else:
        user = User(id=sub, email=email, name=name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


def create_access_token(data: dict, secret_key: str) -> str:
    """Create a new custom JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret_key, algorithm="HS256")

def _decode_jwt(token: str, settings) -> dict:
    """Decode and verify either a custom JWT or Supabase JWT. Raises JWTError if invalid."""
    try:
        # 1. Try custom backend JWT
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"]
        )
    except JWTError:
        # 2. Fallback to Supabase JWT
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_aud": True},
        )


async def _get_or_create_dev_user(session: AsyncSession) -> Optional[User]:
    """Get or create dev user when DEV_AUTH_BYPASS is true."""
    result = await session.execute(select(User).where(User.id == DEV_USER_ID))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(
        id=DEV_USER_ID,
        email="dev@localhost",
        name="Dev User",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
