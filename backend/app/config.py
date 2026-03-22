"""Application configuration from environment."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Settings loaded strictly from environment variables."""

    # =========================
    # Database
    # =========================
    database_url: str

    # =========================
    # Supabase
    # =========================
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str

    # =========================
    # Dev
    # =========================
    dev_auth_bypass: bool = False  # safe default

    # =========================
    # Auth / Security
    # =========================
  #  secret_key: str
    google_client_id: str
    google_client_secret: str
    github_client_id: str
    github_client_secret: str

    # =========================
    # URLs (CRITICAL)
    # =========================
    api_url: str
    frontend_url: str

    # =========================
    # Redis
    # =========================
    redis_url: str

    # =========================
    # LLM (Groq)
    # =========================
    groq_api_key: str
    groq_api_base: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"

    # =========================
    # Embeddings (HF)
    # =========================
    huggingface_api_key: str
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # =========================
    # Webhooks
    # =========================
    slack_signing_secret: str
    github_client_secret: str
    jira_api_token: str
    notion_client_secret: str

    class Config:
        env_file = ".env"  # used locally only
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()