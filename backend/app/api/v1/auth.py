import httpx
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import urllib.parse
import os

from app.api.deps import AsyncSessionDep
from app.config import get_settings
from app.db.models.user import User

from app.services.auth import create_access_token, get_password_hash, verify_password
from app.schemas.user import UserCreate, UserLogin, Token

router = APIRouter()

@router.post("/signup", response_model=Token)
async def signup(session: AsyncSessionDep, user_in: UserCreate):
    result = await session.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user_in.password)
    new_user = User(
        id=str(uuid.uuid4()),
        email=user_in.email,
        hashed_password=hashed_password,
        name=user_in.name
    )
    session.add(new_user)
    await session.commit()
    
    access_token = create_access_token(data={"sub": new_user.id}, secret_key=get_settings().secret_key)
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
async def login(session: AsyncSessionDep, user_in: UserLogin):
    result = await session.execute(select(User).where(User.email == user_in.email))
    user = result.scalar_one_or_none()
    
    if not user or not user.hashed_password or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    access_token = create_access_token(data={"sub": user.id}, secret_key=get_settings().secret_key)
    return {"access_token": access_token, "token_type": "bearer"}

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

@router.get("/google/login")
async def google_login(request: Request):
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=500, detail="Google Client ID/Secret not configured.")

    redirect_uri = f"{settings.api_url}/api/v1/auth/google/callback"

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    
    auth_url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(auth_url)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    session: AsyncSessionDep,
    code: Optional[str] = None,
    error: Optional[str] = None,
):
    settings = get_settings()
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    redirect_uri = f"{settings.api_url}/api/v1/auth/google/callback"

    async with httpx.AsyncClient() as client:
        # 1. Exchange code for token
        data = {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data=data,
            headers={"Accept": "application/json"}
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to fetch token: {token_resp.text}")

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="No access token received")

        # 2. Get user info
        user_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if user_resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to fetch user info")
        
        user_info = user_resp.json()

    email = user_info.get("email")
    name = user_info.get("name")
    if not email:
        raise HTTPException(status_code=400, detail="No email provided by Google")

    # 3. Find or create user
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user:
        if name and user.name != name:
            user.name = name
        await session.flush()
    else:
        user = User(id=str(uuid.uuid4()), email=email, name=name)
        session.add(user)
        await session.flush()
        
    # Commit changes before issuing token
    await session.commit()
    await session.refresh(user)

    # 4. Create custom JWT
    jwt_payload = {
        "sub": user.id,
        "email": user.email,
        "name": user.name
    }
    jwt_token = create_access_token(jwt_payload, settings.secret_key)

    # 5. Redirect to frontend with token
    return RedirectResponse(url=f"{settings.frontend_url}/dashboard?token={jwt_token}")
