"""
The runbook search index: chunks -> vectors -> nearest-neighbour search, with a fingerprint so it is not rebuilt for nothing.

How the pieces fit:
  * Chunks live in SQLite (the source of truth).
  * The vectors are kept in memory and also saved in storage/index/ together with a fingerprint
    (a hash of the chunk texts, the embedding backend and the model name).
  * When the fingerprint of the stored chunks matches, the saved vectors are loaded instead of recomputed.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.tables import IndexState, RunbookChunk, RunbookDocument
from app.rag.embedder import EmbedderChoice, make_embedder
from app.rag.vector_index import VectorIndex, faiss_available

logger = logging.getLogger("triage")
VECTOR_FILE = "runbook_vectors.npy"
STRONG_SCORE, MODERATE_SCORE = 0.30, 0.20  # label bands for TF-IDF similarity; only a guide for the reader


def relevance_label(score: float) -> str:
    return "strong" if score >= STRONG_SCORE else "moderate" if score >= MODERATE_SCORE else "weak"


_FENCED = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def documented_commands(text: str) -> list[str]:
    """Lines from fenced code blocks of a runbook. They are shown to a human as text and are never executed."""
    commands: list[str] = []
    for block in _FENCED.findall(text):
        commands.extend(line.strip() for line in block.splitlines() if line.strip())
    return commands[:20]


class KnowledgeIndex:
    """One per application. Thread-safe: the build is done under a lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._choice: EmbedderChoice | None = None
        self._index: VectorIndex | None = None
        self._rows: list[int] = []  # chunk id for each vector row
        self._fingerprint = ""
        self.builds = 0  # how many times vectors were computed (tests use these two counters)
        self.loads = 0  # how many times saved vectors were reused

    def invalidate(self) -> None:
        """Call after runbooks were added or removed. The next search re-checks the fingerprint."""
        with self._lock:
            self._fingerprint = ""
            self._index = None

    # ------------------------------------------------------------------ building
    def ensure(self, session: Session, settings: Settings) -> None:
        chunks = list(session.scalars(select(RunbookChunk).order_by(RunbookChunk.document_id, RunbookChunk.ordinal)))
        fingerprint = self._fingerprint_of(chunks, settings)
        with self._lock:
            if self._index is not None and self._fingerprint == fingerprint:
                return
            self._choice = make_embedder(settings.embedding_backend, settings.embedding_model)
            embedder = self._choice.embedder
            texts = [self._embed_text(c) for c in chunks]
            embedder.fit(texts)  # TF-IDF learns its vocabulary here (fast); Sentence Transformers does nothing

            state = session.get(IndexState, 1)
            path = settings.index_dir / VECTOR_FILE
            vectors = None
            if state is not None and state.fingerprint == fingerprint and path.exists():
                try:
                    vectors = np.load(path, allow_pickle=False)
                    if len(vectors) != len(chunks):
                        vectors = None
                except Exception:
                    vectors = None  # a damaged file is simply rebuilt
            if vectors is not None:
                self.loads += 1
                self._index = VectorIndex(vectors)
            else:
                vectors = embedder.embed(texts) if texts else np.zeros((0, 1), dtype="float32")
                self._index = VectorIndex(vectors)
                if len(chunks):
                    self._index.save(path)
                self.builds += 1
                self._save_state(session, fingerprint, embedder.name, len(chunks))
            self._rows = [c.id for c in chunks]
            self._fingerprint = fingerprint

    @staticmethod
    def _embed_text(chunk: RunbookChunk) -> str:
        # The heading is part of what the chunk is about, so it is embedded together with the body.
        return f"{chunk.heading}\n{chunk.text}"

    @staticmethod
    def _fingerprint_of(chunks: list[RunbookChunk], settings: Settings) -> str:
        digest = hashlib.sha256()
        digest.update(f"{settings.embedding_backend}|{settings.embedding_model}|{faiss_available()}".encode())
        for c in chunks:
            digest.update(f"|{c.document_id}:{c.ordinal}:{hashlib.sha256(c.text.encode()).hexdigest()}:{c.heading}".encode())
        return digest.hexdigest()

    def _save_state(self, session: Session, fingerprint: str, backend_name: str, count: int) -> None:
        state = session.get(IndexState, 1) or IndexState(id=1)
        state.fingerprint, state.backend = fingerprint, backend_name[:60]
        state.vector_store = self._index.store if self._index else ""
        state.chunk_count, state.built_at = count, datetime.now(timezone.utc).replace(tzinfo=None)
        session.add(state)
        session.commit()

    # ------------------------------------------------------------------ searching
    def search(self, session: Session, settings: Settings, query: str, *, top_k: int, min_relevance: float,
               document_ids: set[str] | None = None) -> dict:
        self.ensure(session, settings)
        assert self._choice is not None and self._index is not None
        info = self.describe(settings)
        query = (query or "").strip()
        if not len(self._index):
            return {"query": query, "results": [], "no_relevant_source": True,
                    "message": "The knowledge base is empty. Load the sample runbooks or upload your own.", **info}
        vector = self._choice.embedder.embed([query])[0]
        # Ask for every row when filtering by document, then cut; the index is small so this is cheap.
        hits = self._index.search(vector, len(self._rows) if document_ids else top_k * 3)
        by_id = {c.id: c for c in session.scalars(select(RunbookChunk).where(RunbookChunk.id.in_([self._rows[i] for i, _ in hits])))}
        docs = {d.id: d for d in session.scalars(select(RunbookDocument))}
        results = []
        for row, score in hits:
            chunk = by_id.get(self._rows[row])
            if chunk is None or score < min_relevance:
                continue
            if document_ids and chunk.document_id not in document_ids:
                continue
            doc = docs[chunk.document_id]
            results.append({
                "rank": len(results) + 1, "score": round(score, 4), "relevance": relevance_label(score), "chunk_id": chunk.id, "document_id": doc.id,
                "document_title": doc.title, "filename": doc.filename, "heading": chunk.heading,
                "citation": f"{doc.filename} › {chunk.heading.split(' > ', 1)[-1] if ' > ' in chunk.heading else chunk.heading}",
                "text": chunk.text, "documented_commands": documented_commands(chunk.text),
                "origin": "runbook",  # retrieved documentation, not an observation about this system
            })
            if len(results) >= top_k:
                break
        message = None if results else (
            "No relevant source was found in the knowledge base for this query. "
            "Nothing below should be treated as documented guidance.")
        return {"query": query, "results": results, "no_relevant_source": not results, "message": message, **info}

    def describe(self, settings: Settings) -> dict:
        choice = self._choice
        return {"retrieval": {
            "requested_backend": settings.embedding_backend,
            "backend": choice.embedder.name if choice else settings.embedding_backend,
            "fallback": bool(choice and choice.fallback_reason),
            "fallback_reason": choice.fallback_reason if choice else None,
            "vector_store": self._index.store if self._index else ("faiss" if faiss_available() else "numpy"),
            "min_relevance": settings.min_relevance,
        }}


def query_from_incident(groups: list[dict], statuses: set[int], slow: bool) -> str:
    """
    Build the search query for an incident from what was observed:
      * the masked message templates of its groups (placeholders such as <NUM> removed),
      * exception type names,
      * words for the HTTP status classes seen (a log says "returned 503"; a runbook says "5xx errors"),
      * "latency" words when a slow duration was observed.
    Log text is untrusted, but here it is only turned into numbers for a similarity search; it is never run or obeyed.
    """
    parts: list[str] = []
    seen: set[str] = set()
    for g in groups:
        template = re.sub(r"<[A-Z]+>", " ", g.get("template") or "")
        if template and template not in seen:
            seen.add(template)
            parts.append(template)
        parts.extend(g.get("exception_types") or [])
    if any(s >= 500 for s in statuses):
        parts.append("HTTP 5xx server errors " + " ".join(str(s) for s in sorted(statuses) if s >= 500))
    if any(s in (401, 403) for s in statuses):
        parts.append("authentication failed unauthorized " + " ".join(str(s) for s in sorted(statuses) if s in (401, 403)))
    if slow:
        parts.append("slow response latency timeout")
    return re.sub(r"\s+", " ", " ".join(parts)).strip()[:1500]
