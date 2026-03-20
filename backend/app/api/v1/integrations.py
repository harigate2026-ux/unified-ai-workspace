"""Integrations list and connect/disconnect."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, AsyncSessionDep
from app.db.models.user import User
from app.schemas.integrations import IntegrationOut, IntegrationConnectIn, IntegrationDisconnectIn
from app.services.integrations_service import (
    list_integrations,
    connect_integration,
    disconnect_integration,
)

router = APIRouter()


@router.get("", response_model=list[IntegrationOut])
async def integrations_list(
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSessionDep,
):
    """GET /api/integrations — list integrations with connection status."""
    items = await list_integrations(session, current_user.id)
    return items


@router.post("/connect")
async def integrations_connect(
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSessionDep,
    body: IntegrationConnectIn,
):
    """POST /api/integrations/connect — connect an integration."""
    features = body.enabled_features or body.connectedApps
    try:
        await connect_integration(
            session,
            current_user.id,
            body.integration_id,
            enabled_features=features,
            email=body.email,
            domain=body.domain,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.post("/disconnect")
async def integrations_disconnect(
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSessionDep,
    body: IntegrationDisconnectIn,
):
    """POST /api/integrations/disconnect — disconnect an integration."""
    await disconnect_integration(session, current_user.id, body.integration_id)
    return {"ok": True}


@router.get("/{provider}/oauth")
async def integration_oauth(
    provider: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """GET /api/integrations/{provider}/oauth"""
    valid_providers = ["github", "slack", "google", "notion", "jira", "microsoft"]
    if provider not in valid_providers:
        raise HTTPException(status_code=400, detail="Invalid provider")
    
    from app.config import get_settings
    settings = get_settings()
    auth_url = f"{settings.api_url}/api/v1/integrations/{provider}/callback?state={current_user.id}&code=mock_oauth_code_123"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=auth_url)


@router.get("/{provider}/callback")
async def integration_oauth_callback(
    provider: str,
    session: AsyncSessionDep,
    state: str = "",
    code: str = "",
):
    """GET /api/integrations/{provider}/callback"""
    from app.db.models.integration import Integration
    from app.db.models.user_integration import UserIntegration
    from sqlalchemy import select
    from fastapi.responses import RedirectResponse
    
    if not state or not code:
        raise HTTPException(status_code=400, detail="Missing state or code")
        
    from app.config import get_settings
    settings = get_settings()
    user_id = state
    
    # Resolve the internal integration UUID based on provider name
    # We map provider strings to the UUIDs generated in 002_seed_integrations.py
    import uuid
    NS = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    
    provider_name_map = {
        "github": "GitHub",
        "slack": "Slack",
        "notion": "Notion",
        "jira": "Jira",
        "google": "Google Workspace",
        "microsoft": "Microsoft Workspace"
    }
    real_name = provider_name_map.get(provider, provider.capitalize())
    integration_id = str(uuid.uuid5(NS, real_name))

    # Check if user_integration already exists
    stmt = select(UserIntegration).where(
        UserIntegration.user_id == user_id, 
        UserIntegration.integration_id == integration_id
    )
    r = await session.execute(stmt)
    existing = r.scalar_one_or_none()
    
    if existing:
        existing.status = "connected"
        existing.config = {"access_token": f"mock_token_{code}", "domain": "example.com"}
    else:
        new_ui = UserIntegration(
            id=str(uuid.uuid4()),
            user_id=user_id,
            integration_id=integration_id,
            status="connected",
            config={"access_token": f"mock_token_{code}", "domain": "example.com"},
        )
        session.add(new_ui)
        
    await session.commit()
    
    if provider == "github":
        from app.services.github_service import sync_github_activity, register_github_webhooks
        await sync_github_activity(session, user_id)
        await register_github_webhooks(session, user_id)
    
    # Redirect back to frontend
    return RedirectResponse(url=f"{settings.frontend_url}/integrations")
