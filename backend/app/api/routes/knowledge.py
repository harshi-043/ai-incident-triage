"""Runbook knowledge base: upload, list, delete and search. Search results always carry a citation."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import check_id, get_app_settings
from app.core.config import Settings
from app.core.database import get_session
from app.core.errors import not_found
from app.models.tables import RunbookDocument
from app.rag.retriever import KnowledgeIndex
from app.services import knowledge_service as service

router = APIRouter(prefix="/knowledge", tags=["knowledge base"])


def get_kb(request: Request) -> KnowledgeIndex:
    return request.app.state.kb


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1500)
    top_k: int = Field(default=5, ge=1, le=20)
    document_ids: list[str] | None = None


@router.get("/status")
def knowledge_status(session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings), kb: KnowledgeIndex = Depends(get_kb)):
    return service.status(session, settings, kb)


@router.get("/documents")
def list_documents(session: Session = Depends(get_session)):
    return {"items": service.list_documents(session)}


@router.post("/documents/upload", status_code=201)
async def upload_document(file: Annotated[UploadFile, File()], session: Session = Depends(get_session),
                          settings: Settings = Depends(get_app_settings), kb: KnowledgeIndex = Depends(get_kb)):
    data = await file.read(settings.max_runbook_bytes + 1)  # never read more than one byte past the limit
    doc, created = service.add_document(session, settings, kb, data, file.filename)
    return {"document": service.document_to_dict(doc), "created": created}


@router.post("/samples", status_code=201)
def load_samples(session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings), kb: KnowledgeIndex = Depends(get_kb)):
    loaded = service.load_sample_runbooks(session, settings, kb)
    return {"items": [service.document_to_dict(d) for d, _ in loaded], "created": sum(1 for _, c in loaded if c),
            "note": "These runbooks are synthetic examples written for this demo."}


@router.get("/documents/{document_id}")
def get_document(document_id: str, session: Session = Depends(get_session)):
    doc = session.get(RunbookDocument, check_id(document_id, "document"))
    if doc is None:
        raise not_found("document", document_id)
    return {"document": service.document_to_dict(doc), "text": doc.text,
            "chunks": [{"id": c.id, "ordinal": c.ordinal, "heading": c.heading, "text": c.text} for c in doc.chunks]}


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: str, session: Session = Depends(get_session), kb: KnowledgeIndex = Depends(get_kb)):
    doc = session.get(RunbookDocument, check_id(document_id, "document"))
    if doc is None:
        raise not_found("document", document_id)
    service.delete_document(session, kb, doc)


@router.post("/search")
def search(body: SearchRequest, session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings),
           kb: KnowledgeIndex = Depends(get_kb)):
    ids = {check_id(i, "document") for i in body.document_ids} if body.document_ids else None
    return kb.search(session, settings, body.query, top_k=body.top_k, min_relevance=settings.min_relevance, document_ids=ids)
