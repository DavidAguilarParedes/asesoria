import hashlib

import pytest

from asesoria.application.retrieval.knowledge_base import KnowledgeBase
from asesoria.application.retrieval.strategies import (
    HybridSearchStrategy,
    SemanticSearchStrategy,
    SparseSearchStrategy,
)
from asesoria.domain.models import DocType, ProcessedChunk, SparseVector
from asesoria.domain.ports import Embedder, SparseEmbedder, VectorStore
from asesoria.infrastructure.vectorstores.qdrant import QdrantStore


def _token_id(token: str) -> int:
    return int(hashlib.md5(token.encode()).hexdigest()[:6], 16)


class FakeDense(Embedder):
    def embed_texts(self, texts):
        out = []
        for t in texts:
            vec = [0.0] * 16
            for token in t.lower().split():
                vec[_token_id(token) % 16] += 1.0
            out.append(vec)
        return out


class FakeSparse(SparseEmbedder):
    def embed_texts(self, texts):
        out = []
        for t in texts:
            ids = sorted({_token_id(tok) for tok in t.lower().split()})
            out.append(SparseVector(indices=ids, values=[1.0] * len(ids)))
        return out


CHUNKS = [
    ("tlt-1", "TLT effective duration 14.63 years long treasury", "TLT"),
    ("shy-1", "SHY effective duration 1.84 years short treasury", "SHY"),
    ("agg-1", "AGG aggregate bond expense ratio 0.03", "AGG"),
]


def chunks() -> list[ProcessedChunk]:
    return [
        ProcessedChunk(chunk_id=c, content=t, doc_id=c, doc_type=DocType.FACT_SHEET, ticker=tk)
        for c, t, tk in CHUNKS
    ]


def make_kb(store: VectorStore) -> KnowledgeBase:
    store.reset()
    kb = KnowledgeBase(FakeDense(), store, FakeSparse())
    kb.index(chunks())
    return kb


def test_all_strategies_find_the_right_chunk(tmp_path):
    kb = make_kb(QdrantStore(tmp_path / "q", "test", dim=16))
    strategies = (SemanticSearchStrategy, SparseSearchStrategy, HybridSearchStrategy)
    for strategy in strategies:
        results = strategy(kb).retrieve_context("TLT effective duration", {}, k=2)
        assert results[0].chunk_id == "tlt-1", strategy.__name__
        assert isinstance(results[0], ProcessedChunk)


def test_metadata_filter(tmp_path):
    kb = make_kb(QdrantStore(tmp_path / "q", "test", dim=16))
    results = HybridSearchStrategy(kb).retrieve_context("effective duration", {"ticker": "SHY"}, 3)
    assert [c.chunk_id for c in results] == ["shy-1"]


class RecordingStore(VectorStore):
    supports_sparse = True

    def reset(self):
        self.received = None

    def index(self, ids, dense, sparse, payloads):
        self.received = (ids, dense, sparse, payloads)

    def search_dense(self, vector, filters, k):
        return []


def test_store_only_receives_primitives():
    # Regla del Bridge: la implementación no conoce Pydantic
    store = RecordingStore()
    make_kb(store)
    ids, dense, sparse, payloads = store.received
    assert all(isinstance(i, str) for i in ids)
    assert all(isinstance(v, list) for v in dense)
    assert all(isinstance(s, tuple) for s in sparse)
    assert all(isinstance(p, dict) for p in payloads)
    assert not any(isinstance(x, ProcessedChunk) for x in payloads)


class InMemoryStore(VectorStore):
    """Implementación mínima solo para probar que el Bridge permite cambiar la tecnología."""

    def reset(self):
        self.rows = []

    def index(self, ids, dense, sparse, payloads):
        self.rows += list(zip(dense, payloads, strict=True))

    def search_dense(self, vector, filters, k):
        def cosine(a, b):
            dot = sum(x * y for x, y in zip(a, b, strict=True))
            norm = (sum(x * x for x in a) * sum(y * y for y in b)) ** 0.5
            return dot / norm if norm else 0.0

        rows = [
            {**payload, "score": cosine(vector, vec)}
            for vec, payload in self.rows
            if all(payload.get(key) == value for key, value in filters.items() if value)
        ]
        return sorted(rows, key=lambda r: r["score"], reverse=True)[:k]


def test_same_strategy_works_with_another_store():
    # Sin tocar KnowledgeBase ni las estrategias, solo cambiando la implementación
    kb = make_kb(InMemoryStore())
    assert kb.sparse is None
    results = SemanticSearchStrategy(kb).retrieve_context("TLT effective duration", {}, 2)
    assert results[0].chunk_id == "tlt-1"
    filtered = SemanticSearchStrategy(kb).retrieve_context("duration", {"ticker": "SHY"}, 3)
    assert [c.chunk_id for c in filtered] == ["shy-1"]
    with pytest.raises(NotImplementedError):
        HybridSearchStrategy(kb).retrieve_context("TLT", {}, 2)
