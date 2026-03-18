"""Background job handlers: index_document, generate_workspace_summary, etc."""
import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.db.models.document import Document
from app.db.models.document_chunk import DocumentChunk
from app.ai.embeddings import embed_text
from app.config import get_settings

CHUNK_SIZE = 512
OVERLAP = 100


async def index_document(document_id: str) -> None:
    """Chunk document content, embed, insert document_chunks."""
    async with async_session_factory() as session:
        r = await session.execute(select(Document).where(Document.id == document_id))
        doc = r.scalar_one_or_none()
        if not doc or not doc.content:
            return
        content = doc.content
        source = doc.source
        url = doc.url or "#"
        user_id = doc.user_id

        # Simple chunking by character (could use tokenizer later)
        chunks = []
        start = 0
        idx = 0
        while start < len(content):
            end = min(start + CHUNK_SIZE, len(content))
            chunk_text = content[start:end]
            if chunk_text.strip():
                chunks.append((idx, chunk_text))
                idx += 1
            start = end - OVERLAP if end < len(content) else len(content)

        for chunk_index, chunk_text in chunks:
            embedding = await embed_text(chunk_text)
            chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=document_id,
                content=chunk_text,
                embedding=embedding if embedding else None,
                source=source,
                url=url,
                chunk_index=chunk_index,
            )
            session.add(chunk)
        await session.commit()


async def generate_workspace_summary(user_id: str) -> None:
    """Placeholder: generate AI summary for dashboard (could call LLM and cache)."""
    # Phase 9 can implement: call LLM over tasks/messages/activity, cache in Redis
    pass


async def prioritize_tasks(user_id: str) -> None:
    """Placeholder: reorder or score tasks (could call LLM)."""
    pass


from app.worker.ingestion_tasks import ingest_data

def run_job(job_type: str, payload: dict) -> None:
    """Sync entrypoint that runs async job (for worker process)."""
    import asyncio
    if job_type == "index_document":
        asyncio.run(index_document(payload.get("document_id", "")))
    elif job_type == "generate_workspace_summary":
        asyncio.run(generate_workspace_summary(payload.get("user_id", "")))
    elif job_type == "prioritize_tasks":
        asyncio.run(prioritize_tasks(payload.get("user_id", "")))
    elif job_type == "ingest_data":
        asyncio.run(ingest_data(payload.get("user_id", ""), payload.get("integration_name", "")))

