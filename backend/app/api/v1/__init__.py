"""API v1 — all routes under /api."""
from fastapi import APIRouter

from app.api.v1 import users, dashboard, activity, events, search, integrations, assistant, webhooks, auth, github

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])

router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
router.include_router(activity.router, prefix="/activity", tags=["activity"])
router.include_router(events.router, prefix="/events", tags=["events"])
router.include_router(search.router, prefix="/search", tags=["search"])
router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
router.include_router(assistant.router, prefix="/assistant", tags=["assistant"])
router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
router.include_router(github.router, prefix="/github", tags=["github"])
