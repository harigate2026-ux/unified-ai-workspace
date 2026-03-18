"""Embedding generation using HuggingFace sentence-transformers."""

from sentence_transformers import SentenceTransformer
from app.config import get_settings

_settings = get_settings()

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(_settings.embedding_model)
    return _model


async def embed_text(text: str) -> list[float]:
    """Return embedding vector for text."""
    
    if not text.strip():
        return [0.0] * _settings.embedding_dimension

    model = _get_model()

    embedding = model.encode(text.strip())

    return embedding.tolist()