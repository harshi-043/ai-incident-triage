"""
A small vector index. Vectors are L2-normalised, so the inner product equals cosine similarity.

FAISS (IndexFlatIP, exact search) is used when it can be imported. If not, a NumPy version gives the same results.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

try:  # faiss-cpu is in requirements.txt, but the app must still work without it
    import faiss  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - depends on the machine
    faiss = None


def faiss_available() -> bool:
    return faiss is not None


class VectorIndex:
    """Exact nearest-neighbour search over a few thousand vectors."""

    def __init__(self, vectors: np.ndarray, *, use_faiss: bool = True) -> None:
        self.vectors = np.ascontiguousarray(vectors, dtype="float32")
        self.store = "faiss" if (use_faiss and faiss is not None and len(self.vectors)) else "numpy"
        self._faiss = None
        if self.store == "faiss":
            self._faiss = faiss.IndexFlatIP(self.vectors.shape[1])
            self._faiss.add(self.vectors)

    def __len__(self) -> int:
        return len(self.vectors)

    def search(self, query: np.ndarray, k: int) -> list[tuple[int, float]]:
        """Return up to k (row number, similarity) pairs, best first."""
        if not len(self.vectors):
            return []
        k = max(1, min(k, len(self.vectors)))
        q = np.ascontiguousarray(query.reshape(1, -1), dtype="float32")
        if self._faiss is not None:
            scores, ids = self._faiss.search(q, k)
            return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i >= 0]
        scores = (self.vectors @ q[0])
        order = np.argsort(-scores, kind="stable")[:k]
        return [(int(i), float(scores[i])) for i in order]

    # ---- saving: the vectors are stored as one .npy file; the FAISS index is rebuilt from them in milliseconds ----
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp.npy")
        np.save(tmp, self.vectors, allow_pickle=False)
        tmp.replace(path)  # replace the old file in one step, so a crash never leaves half a file

    @classmethod
    def load(cls, path: Path, *, use_faiss: bool = True) -> "VectorIndex":
        return cls(np.load(path, allow_pickle=False), use_faiss=use_faiss)
