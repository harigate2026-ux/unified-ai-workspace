"""Supabase JWT verification and current user resolution."""
from typing import Optional
from datetime import datetime

from fastapi import Request
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.user import User

# Dev user id when DEV_AUTH_BYPASS is True
DEV_USER_ID = "dev-user"


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
    Single source of truth: Supabase JWT.
    """
    settings = get_settings()
    token = _get_bearer_token(request)

    # 1. Dev bypass: no token or invalid token -> use dev user
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

    # Upsert user based on Supabase sub
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


def _decode_jwt(token: str, settings) -> dict:
    """Decode and verify Supabase JWT only. Raises JWTError if invalid."""
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
