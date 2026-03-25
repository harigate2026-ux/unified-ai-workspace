"""Auth API — Placeholder for Supabase-only architecture."""
from fastapi import APIRouter

router = APIRouter()

# Manual signup/login and Google OAuth routes have been removed.
# Authentication is now handled exclusively by Supabase on the frontend.
# The backend verifies the Supabase JWT in protected routes using the get_current_user dependency.
