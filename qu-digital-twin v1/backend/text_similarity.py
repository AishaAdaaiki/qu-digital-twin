"""
Minimal TF-IDF + cosine similarity, dependency-free beyond numpy (no scikit-learn,
no network calls, fully deterministic). Backs the M9 new-elective feasibility
engine's similarity scoring (docs/department_simulation_architecture.md §5).

This is intentionally simple: lowercase + strip punctuation + split on whitespace,
English stopword removal, raw TF-IDF weighting, cosine similarity. It's a document-
similarity heuristic for ranking a few dozen course descriptions, not a general NLP
pipeline - if the corpus ever grows to hundreds of courses, swapping this for an
embedding model would be a drop-in replacement (same "text in, ranked list out"
call shape).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Tuple

import numpy as np

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "is",
    "are", "as", "by", "at", "from", "this", "that", "these", "those", "be",
    "will", "into", "using", "used", "its", "their", "an", "it", "including",
    "such", "based", "which", "than", "then", "over", "under", "between",
}

_TOKEN_RE = re.compile(r"[a-z]+")


def tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2]


class TfidfIndex:
    """Build once over a corpus of {doc_id: text}, then query with new text."""

    def __init__(self, documents: Dict[str, str]):
        self.doc_ids = list(documents.keys())
        self._doc_tokens = {doc_id: tokenize(text) for doc_id, text in documents.items()}

        vocab = sorted({tok for toks in self._doc_tokens.values() for tok in toks})
        self.vocab_index = {tok: i for i, tok in enumerate(vocab)}
        n_docs = len(documents)

        doc_freq = Counter()
        for toks in self._doc_tokens.values():
            doc_freq.update(set(toks))
        self.idf = np.array(
            [math.log((1 + n_docs) / (1 + doc_freq[tok])) + 1 for tok in vocab]
        )

        self.doc_vectors = np.zeros((n_docs, len(vocab)))
        for i, doc_id in enumerate(self.doc_ids):
            self.doc_vectors[i] = self._vectorize(self._doc_tokens[doc_id])

    def _vectorize(self, tokens: List[str]) -> np.ndarray:
        vec = np.zeros(len(self.vocab_index))
        counts = Counter(tokens)
        for tok, count in counts.items():
            idx = self.vocab_index.get(tok)
            if idx is not None:
                vec[idx] = count
        return vec * self.idf

    def query(self, text: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """Returns [(doc_id, cosine_similarity), ...] sorted descending, length <= top_k.
        Docs with zero vocabulary overlap are excluded rather than returned at 0.0."""
        query_vec = self._vectorize(tokenize(text))
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []

        doc_norms = np.linalg.norm(self.doc_vectors, axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            sims = (self.doc_vectors @ query_vec) / (doc_norms * query_norm)
        sims = np.nan_to_num(sims)

        ranked = sorted(zip(self.doc_ids, sims), key=lambda x: x[1], reverse=True)
        return [(doc_id, float(score)) for doc_id, score in ranked if score > 0][:top_k]
