"""Application configuration from environment."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Settings loaded from .env."""

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/unified_ai_dashboard"

    # Supabase
    supabase_url: str = "https://placeholder.supabase.co"
    supabase_jwt_secret: str = "placeholder-secret"
    supabase_anon_key: str = ""

    # Dev auth bypass (local only)
    #dev_auth_bypass: bool = False #-- changed 
    dev_auth_bypass: bool = False

    # Auth
    secret_key: str = "your-super-secret-key"
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    frontend_url: str = "http://localhost:5173"
    api_url: str = "http://localhost:8000"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM
    # openai_api_key: str = ""
    # openai_api_base: str = "https://api.openai.com/v1"
    # openai_model: str = "gpt-4o-mini"

    # # Embeddings
    # embedding_model: str = "text-embedding-3-small"
    # embedding_dimension: int = 1536
    # LLM - Groq
    groq_api_key: str = ""
    groq_api_base: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"

    # Embeddings - HuggingFace
    huggingface_api_key: str = ""
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # Webhooks
    slack_signing_secret: str = ""
    github_webhook_secret: str = ""
    jira_webhook_secret: str = ""
    notion_webhook_secret: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
