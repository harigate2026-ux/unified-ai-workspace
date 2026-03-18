"""Webhook receivers: Slack, GitHub, Jira, Notion. Verify signature, normalize, store events."""
import hmac
import hashlib
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Header
from sqlalchemy import select

from app.config import get_settings
from app.db.session import async_session_factory
from app.db.models.event import Event
from app.db.models.user import User

router = APIRouter()


def _get_user_id_from_request(request: Request, x_user_id: str | None = None) -> str | None:
    """Resolve user_id for webhook: header X-User-Id (dev) or first user (dev)."""
    if x_user_id:
        return x_user_id
    # Optional: parse body for workspace id and look up user_integrations
    return None


async def _store_workspace_activity(user_id: str, source: str, event_type: str, title: str, description: str, actor: str, url: str | None = None) -> None:
    from app.db.models.workspace_activity import WorkspaceActivity
    async with async_session_factory() as session:
        r = await session.execute(select(User).where(User.id == user_id))
        if r.scalar_one_or_none() is None:
            return
        dt = datetime.utcnow()
        activity = WorkspaceActivity(
            id=str(uuid.uuid4()),
            user_id=user_id,
            type=str(event_type)[:32] if event_type else "event",
            title=str(title)[:512] if title else "",
            description=str(description)[:1024] if description else "",
            source=str(source)[:64] if source else "unknown",
            actor=str(actor)[:255] if actor else "system",
            event_at=dt,
            url=url,
            created_at=dt
        )
        session.add(activity)
        await session.commit()


# ---- Slack ----
def _verify_slack(request: Request, body: bytes, secret: str) -> bool:
    """Verify X-Slack-Signature: v0=<hmac_sha256(body)>."""
    sig = request.headers.get("X-Slack-Signature", "")
    if not sig.startswith("v0="):
        return False
    expected = "v0=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


@router.post("/slack")
async def webhook_slack(
    request: Request,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """POST /api/webhooks/slack — verify signature, normalize, store event."""
    body = await request.body()
    settings = get_settings()
    if settings.slack_signing_secret and not _verify_slack(request, body, settings.slack_signing_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    # Normalize: type, text, user, etc.
    event_type = data.get("type", "message")
    event_payload = data.get("event") or {}
    event_text = event_payload.get("text", "") if isinstance(event_payload, dict) else str(data)[:200]
    if not event_text:
        event_text = f"Slack {event_type}"
    actor = event_payload.get("user", "Slack") if isinstance(event_payload, dict) else "Slack"
    user_id = _get_user_id_from_request(request, x_user_id)
    if user_id:
        await _store_workspace_activity(user_id, "Slack", event_type, f"Slack {event_type}", event_text, actor, None)
    return {"ok": True}


# ---- GitHub ----
def _verify_github(payload: bytes, signature: str, secret: str) -> bool:
    """Verify X-Hub-Signature-256: sha256=<hmac_sha256(payload)>."""
    if not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


@router.post("/github")
async def webhook_github(
    request: Request,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """POST /api/webhooks/github — verify signature, normalize, store event."""
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    settings = get_settings()
    if settings.github_webhook_secret and not _verify_github(body, sig, settings.github_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    action = data.get("action", "")
    event_name = request.headers.get("X-GitHub-Event", "event")
    repo = data.get("repository", {}).get("full_name", "repo")
    sender = data.get("sender", {}).get("login", "GitHub")

    if event_name == "push":
        commits = data.get("commits", [])
        desc = f"Pushed {len(commits)} commits"
        url = data.get("compare", "")
    elif event_name == "pull_request":
        desc = data.get("pull_request", {}).get("title", "")
        url = data.get("pull_request", {}).get("html_url", "")
    elif event_name == "issues":
        desc = data.get("issue", {}).get("title", "")
        url = data.get("issue", {}).get("html_url", "")
    else:
        desc = f"{event_name} on {repo}"
        url = ""

    title = f"GitHub {action or event_name}: {repo}"
    
    # Store workspace activity
    user_id = _get_user_id_from_request(request, x_user_id)
    if user_id:
        await _store_workspace_activity(user_id, "GitHub", event_name, title, desc, sender, url)
    
    # Process for RAG
    from app.services.github_service import process_github_webhook
    async with async_session_factory() as session:
        await process_github_webhook(session, data, event_name)
        
    return {"ok": True}


# ---- Jira ----
def _verify_jira(request: Request, body: bytes, secret: str) -> bool:
    """Optional: Jira often uses HMAC or shared secret in header."""
    if not secret:
        return True
    # Jira webhook secret can be sent in X-Webhook-Secret or similar
    provided = request.headers.get("X-Webhook-Secret", "")
    return hmac.compare_digest(provided, secret)


@router.post("/jira")
async def webhook_jira(
    request: Request,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """POST /api/webhooks/jira — verify (if configured), normalize, store event."""
    body = await request.body()
    settings = get_settings()
    if settings.jira_webhook_secret and not _verify_jira(request, body, settings.jira_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    webhook_event = data.get("webhookEvent", "jira")
    issue = data.get("issue", {})
    key = issue.get("key", "")
    desc = issue.get("fields", {}).get("summary", "")
    actor = data.get("user", {}).get("displayName", "Jira") or "Jira"
    url = f"/browse/{key}" if key else ""

    title = f"Jira {webhook_event}: {key}"
    user_id = _get_user_id_from_request(request, x_user_id)
    if user_id:
        await _store_workspace_activity(user_id, "Jira", webhook_event, title, desc, actor, url)
    return {"ok": True}


# ---- Notion ----
def _verify_notion(request: Request, body: bytes, secret: str) -> bool:
    if not secret:
        return True
    # Notion uses X-Notion-Signature or similar
    provided = request.headers.get("X-Notion-Signature", "")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


@router.post("/notion")
async def webhook_notion(
    request: Request,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """POST /api/webhooks/notion — verify (if configured), normalize, store event."""
    body = await request.body()
    settings = get_settings()
    if settings.notion_webhook_secret and not _verify_notion(request, body, settings.notion_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    event_text = "Notion update"
    user_id = _get_user_id_from_request(request, x_user_id)
    if user_id:
        await _store_workspace_activity(user_id, "Notion", "update", "Notion update", event_text, "Notion", None)
    return {"ok": True}
