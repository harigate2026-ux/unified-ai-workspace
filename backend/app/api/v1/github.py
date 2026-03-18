"""GitHub OAuth endpoints."""
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import get_current_user, AsyncSessionDep
from app.db.models.user import User
from app.db.models.integration import Integration
from app.db.models.user_integration import UserIntegration
from app.config import get_settings
from app.services.github_service import (
    exchange_github_code,
    get_github_user,
    sync_github_activity,
    register_github_webhooks
)

router = APIRouter()

@router.get("/connect")
async def github_connect(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """GET /api/v1/github/connect — redirect to GitHub OAuth."""
    settings = get_settings()
    if not settings.github_client_id:
        raise HTTPException(status_code=500, detail="GitHub Client ID not configured")
    
    # scope: repo for full access, read:user for profile
    scope = "repo read:user user:email"
    auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&scope={scope}"
        f"&state={current_user.id}"
    )
    return RedirectResponse(url=auth_url)

@router.get("/callback")
async def github_callback(
    session: AsyncSessionDep,
    code: str = Query(None),
    state: str = Query(None),
):
    """GET /api/v1/github/callback — handle GitHub OAuth callback."""
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")
    
    user_id = state
    access_token = await exchange_github_code(code)
    if not access_token:
        raise HTTPException(status_code=400, detail="Failed to exchange GitHub code")
    
    github_user = await get_github_user(access_token)
    if not github_user:
        raise HTTPException(status_code=400, detail="Failed to fetch GitHub user")
    
    # Resolve the internal integration UUID for GitHub
    # We map provider strings to the UUIDs generated in seeders
    NS = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    integration_id = str(uuid.uuid5(NS, "GitHub"))

    # Check if integration exists in the database
    stmt = select(Integration).where(Integration.name == "GitHub")
    r = await session.execute(stmt)
    integ = r.scalar_one_or_none()
    if not integ:
        # If not found by name, use the generated UUID
        integration_id = str(uuid.uuid5(NS, "GitHub"))
    else:
        integration_id = integ.id

    # Check if user_integration already exists
    stmt = select(UserIntegration).where(
        UserIntegration.user_id == user_id, 
        UserIntegration.integration_id == integration_id
    )
    r = await session.execute(stmt)
    existing = r.scalar_one_or_none()
    
    config = {
        "access_token": access_token,
        "github_user_id": github_user.get("id"),
        "github_login": github_user.get("login")
    }
    
    if existing:
        existing.status = "connected"
        existing.config = config
        from datetime import datetime
        existing.updated_at = datetime.utcnow()
    else:
        new_ui = UserIntegration(
            id=str(uuid.uuid4()),
            user_id=user_id,
            integration_id=integration_id,
            status="connected",
            config=config,
        )
        session.add(new_ui)
        
    await session.commit()
    
    # Sync activity and register webhooks
    await sync_github_activity(session, user_id)
    await register_github_webhooks(session, user_id)
    
    settings = get_settings()
    return RedirectResponse(url=f"{settings.frontend_url}/integrations")
