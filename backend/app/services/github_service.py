import uuid
from datetime import datetime
import asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models.user_integration import UserIntegration
from app.db.models.integration import Integration
from app.db.models.workspace_activity import WorkspaceActivity
from app.db.models.user import User
from app.db.models.document import Document

from app.config import get_settings

async def exchange_github_code(code: str) -> str | None:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            }
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("access_token")

async def get_github_user(access_token: str) -> dict | None:
    headers = {
        "Authorization": f"token {access_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://api.github.com/user", headers=headers)
        if resp.status_code != 200:
            return None
        return resp.json()

async def sync_github_activity(session: AsyncSession, user_id: str):
    # 1. Get user integration for GitHub
    stmt = (
        select(UserIntegration)
        .join(Integration)
        .where(UserIntegration.user_id == user_id)
        .where(Integration.name == "GitHub")
    )
    result = await session.execute(stmt)
    user_integration = result.scalar_one_or_none()

    if not user_integration or not user_integration.config or "access_token" not in user_integration.config:
        return

    access_token = user_integration.config["access_token"]
    headers = {
        "Authorization": f"token {access_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    from app.worker.tasks import index_document

    async with httpx.AsyncClient() as client:
        # GET /user/repos
        repos_resp = await client.get("https://api.github.com/user/repos", headers=headers)
        if repos_resp.status_code != 200:
            return
        repos = repos_resp.json()

        for repo in repos:
            owner = repo["owner"]["login"]
            repo_name = repo["name"]

            # GET /repos/{owner}/{repo}/issues
            issues_resp = await client.get(f"https://api.github.com/repos/{owner}/{repo_name}/issues", headers=headers)
            if issues_resp.status_code == 200:
                issues = issues_resp.json()
                for issue in issues:
                    if "pull_request" not in issue: # skip PRs in issues response
                        # Add to workspace activity
                        await add_github_event(
                            session=session,
                            user_id=user_id,
                            title=issue["title"],
                            description=f"Issue #{issue['number']}",
                            url=issue["html_url"],
                            type="comment",
                            actor=issue["user"]["login"],
                            created_at=issue["created_at"]
                        )
                        # Add to Document (RAG)
                        doc = await add_github_document(
                            session=session,
                            user_id=user_id,
                            external_id=f"github-issue-{issue['id']}",
                            title=issue["title"],
                            content=issue.get("body") or "",
                            url=issue["html_url"],
                            repo=repo["full_name"],
                            author=issue["user"]["login"],
                            event_type="issue"
                        )
                        if doc:
                            # Trigger background task for indexing
                            from app.services.queue import enqueue
                            enqueue("index_document", {"document_id": doc.id})
            
            # GET /repos/{owner}/{repo}/pulls
            pulls_resp = await client.get(f"https://api.github.com/repos/{owner}/{repo_name}/pulls", headers=headers)
            if pulls_resp.status_code == 200:
                pulls = pulls_resp.json()
                for pr in pulls:
                    # Add to workspace activity
                    await add_github_event(
                        session=session,
                        user_id=user_id,
                        title=pr["title"],
                        description=f"PR #{pr['number']}",
                        url=pr["html_url"],
                        type="pr",
                        actor=pr["user"]["login"],
                        created_at=pr["created_at"]
                    )
                    # Add to Document (RAG)
                    doc = await add_github_document(
                        session=session,
                        user_id=user_id,
                        external_id=f"github-pr-{pr['id']}",
                        title=pr["title"],
                        content=pr.get("body") or "",
                        url=pr["html_url"],
                        repo=repo["full_name"],
                        author=pr["user"]["login"],
                        event_type="pull_request"
                    )
                    if doc:
                        # Trigger background task for indexing
                        from app.services.queue import enqueue
                        enqueue("index_document", {"document_id": doc.id})
        
        await session.commit()

async def add_github_event(session: AsyncSession, user_id: str, title: str, description: str, url: str, type: str, actor: str, created_at: str):
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except:
        dt = datetime.utcnow()
        
    activity = WorkspaceActivity(
        id=str(uuid.uuid4()),
        user_id=user_id,
        source="GitHub",
        title=title,
        description=description,
        url=url,
        type=type,
        actor=actor,
        event_at=dt,
        created_at=dt
    )
    session.add(activity)

async def add_github_document(
    session: AsyncSession, 
    user_id: str, 
    external_id: str, 
    title: str, 
    content: str, 
    url: str,
    repo: str,
    author: str,
    event_type: str
) -> Document | None:
    # Check if document already exists
    stmt = select(Document).where(Document.external_id == external_id)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        existing.title = title
        existing.content = content
        existing.url = url
        existing.updated_at = datetime.utcnow()
        return existing
    
    doc = Document(
        id=str(uuid.uuid4()),
        user_id=user_id,
        source="GitHub",
        external_id=external_id,
        title=title,
        content=content,
        url=url,
    )
    session.add(doc)
    return doc

async def process_github_webhook(session: AsyncSession, payload: dict, event_type: str):
    """Process incoming GitHub webhook and convert to Document."""
    # We need to find the user_id for this repository
    repo_full_name = payload.get("repository", {}).get("full_name")
    if not repo_full_name:
        return

    # Find UserIntegration by repository metadata (if we stored it) or look for any user that has access to this repo
    # For MVP, we can lookup users that have GitHub integration connected
    stmt = (
        select(UserIntegration)
        .join(Integration)
        .where(Integration.name == "GitHub")
        .where(UserIntegration.status == "connected")
    )
    result = await session.execute(stmt)
    user_integrations = result.scalars().all()
    
    # In a real system, we'd store which user owns which repo hooks.
    # For now, we'll try to find the user who has the token that can access this repo, 
    # or just use the first user for demonstration if there's only one.
    if not user_integrations:
        return
        
    user_id = user_integrations[0].user_id # MVP simplification

    doc = None
    if event_type == "issues":
        issue = payload.get("issue", {})
        doc = await add_github_document(
            session=session,
            user_id=user_id,
            external_id=f"github-issue-{issue['id']}",
            title=issue["title"],
            content=issue.get("body") or "",
            url=issue["html_url"],
            repo=repo_full_name,
            author=issue["user"]["login"],
            event_type="issue"
        )
    elif event_type == "pull_request":
        pr = payload.get("pull_request", {})
        doc = await add_github_document(
            session=session,
            user_id=user_id,
            external_id=f"github-pr-{pr['id']}",
            title=pr["title"],
            content=pr.get("body") or "",
            url=pr["html_url"],
            repo=repo_full_name,
            author=pr["user"]["login"],
            event_type="pull_request"
        )
    elif event_type == "push":
        commits = payload.get("commits", [])
        for commit in commits:
            doc = await add_github_document(
                session=session,
                user_id=user_id,
                external_id=f"github-commit-{commit['id']}",
                title=f"Commit in {repo_full_name}",
                content=commit.get("message") or "",
                url=commit["url"],
                repo=repo_full_name,
                author=commit["author"]["name"],
                event_type="commit"
            )
            if doc:
                from app.services.queue import enqueue
                enqueue("index_document", {"document_id": doc.id})
        return # already enqueued in the loop

    if doc:
        from app.services.queue import enqueue
        enqueue("index_document", {"document_id": doc.id})
    
    await session.commit()

async def register_github_webhooks(session: AsyncSession, user_id: str):
    stmt = (
        select(UserIntegration)
        .join(Integration)
        .where(UserIntegration.user_id == user_id)
        .where(Integration.name == "GitHub")
    )
    result = await session.execute(stmt)
    user_integration = result.scalar_one_or_none()

    if not user_integration or not user_integration.config or "access_token" not in user_integration.config:
        return

    access_token = user_integration.config["access_token"]
    headers = {
        "Authorization": f"token {access_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    
    settings = get_settings()

    webhook_url = f"{settings.api_url}/api/webhooks/github"  # placeholder base url

    async with httpx.AsyncClient() as client:
        repos_resp = await client.get("https://api.github.com/user/repos", headers=headers)
        if repos_resp.status_code == 200:
            repos = repos_resp.json()
            for repo in repos:
                owner = repo["owner"]["login"]
                repo_name = repo["name"]
                
                hook_data = {
                    "name": "web",
                    "active": True,
                    "events": ["push", "pull_request", "issues"],
                    "config": {
                        "url": webhook_url,
                        "content_type": "json",
                        "insecure_ssl": "0"
                    }
                }
                
                from app.config import get_settings
                settings = get_settings()
                if settings.github_webhook_secret:
                    hook_data["config"]["secret"] = settings.github_webhook_secret
                
                await client.post(
                    f"https://api.github.com/repos/{owner}/{repo_name}/hooks",
                    headers=headers,
                    json=hook_data
                )

