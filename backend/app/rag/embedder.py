"""
Turn text into vectors.

  TfidfEmbedder               always available, no download. Matches words, so a paraphrase with different words scores low.
  SentenceTransformerEmbedder optional. Understands meaning better, but needs the 'sentence-transformers' package and a
                              one-time model download. NOT tested in the project's build environment (no internet access
                              to the model host there); the fallback path to TF-IDF is tested.

`make_embedder` never raises for a missing optional backend: it falls back to TF-IDF and says so (`fallback_reason`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

logger = logging.getLogger("triage")


class TfidfEmbedder:
    name = "tfidf"

    def __init__(self) -> None:
        # Words and word pairs; sublinear tf damps repeated words. Keywords such as "HikariPool" stay whole.
        self._vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), sublinear_tf=True, max_features=8000,
                                           token_pattern=r"(?u)\b[\w][\w.\-]+\b|\b\w\b", stop_words="english")
        self._fitted = False

    def fit(self, texts: list[str]) -> None:
        """Learn the vocabulary from the runbook chunks. Must be called before `embed`."""
        if not texts:
            self._fitted = False
            return
        self._vectorizer.fit(texts)
        self._fitted = True

    def embed(self, texts: list[str]) -> np.ndarray:
        if not self._fitted:
            return np.zeros((len(texts), 1), dtype="float32")
        matrix = self._vectorizer.transform(texts)  # already L2-normalised by scikit-learn
        return matrix.toarray().astype("float32")


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # imported here: the package is optional

        self.name = f"sentence_transformers:{model_name}"
        self._model = SentenceTransformer(model_name)

    def fit(self, texts: list[str]) -> None:  # nothing to learn: the model is pre-trained
        return None

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype="float32")


@dataclass
class EmbedderChoice:
    embedder: TfidfEmbedder | SentenceTransformerEmbedder
    requested: str
    fallback_reason: str | None  # set when the requested backend could not be used


def make_embedder(backend: str, model_name: str) -> EmbedderChoice:
    if backend == "sentence_transformers":
        try:
            return EmbedderChoice(SentenceTransformerEmbedder(model_name), backend, None)
        except Exception as exc:  # missing package, no network for the download, bad model name ...
            reason = f"{type(exc).__name__}: {str(exc)[:160]}"
            logger.warning("Sentence Transformers is not usable (%s). Using TF-IDF instead.", reason)
            return EmbedderChoice(TfidfEmbedder(), backend, reason)
    if backend != "tfidf":
        return EmbedderChoice(TfidfEmbedder(), backend, f"Unknown embedding backend '{backend}'.")
    return EmbedderChoice(TfidfEmbedder(), backend, None)
