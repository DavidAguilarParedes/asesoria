import hashlib

from asesoria.application.retrieval.knowledge_base import KnowledgeBase
from asesoria.application.retrieval.strategies import DenseSearch, HybridSearch, SparseSearch
from asesoria.domain.models import DocType, ProcessedChunk, SparseVector
from asesoria.domain.ports import Embedder, SparseEmbedder
from asesoria.infrastructure.vectorstores.qdrant import QdrantStore


def _token_id(token: str) -> int:
    return int(hashlib.md5(token.encode()).hexdigest()[:6], 16)


class FakeDense(Embedder):
    def embed(self, texts):
        out = []
        for t in texts:
            vec = [0.0] * 16
            for token in t.lower().split():
                vec[_token_id(token) % 16] += 1.0
            out.append(vec)
        return out


class FakeSparse(SparseEmbedder):
    def embed(self, texts):
        out = []
        for t in texts:
            ids = sorted({_token_id(tok) for tok in t.lower().split()})
            out.append(SparseVector(indices=ids, values=[1.0] * len(ids)))
        return out


def chunk(cid: str, text: str, ticker: str) -> ProcessedChunk:
    return ProcessedChunk(
        chunk_id=cid, content=text, doc_id=cid, doc_type=DocType.FACT_SHEET, ticker=ticker
    )


def make_kb(tmp_path) -> KnowledgeBase:
    store = QdrantStore(tmp_path / "q", "test", dim=16)
    store.reset()
    kb = KnowledgeBase(FakeDense(), FakeSparse(), store)
    kb.index(
        [
            chunk("tlt-1", "TLT effective duration 14.63 years long treasury", "TLT"),
            chunk("shy-1", "SHY effective duration 1.84 years short treasury", "SHY"),
            chunk("agg-1", "AGG aggregate bond expense ratio 0.03", "AGG"),
        ]
    )
    return kb


def test_all_strategies_find_the_right_chunk(tmp_path):
    kb = make_kb(tmp_path)
    for strategy in (DenseSearch(kb), SparseSearch(kb), HybridSearch(kb)):
        results = strategy.retrieve("TLT effective duration", {}, k=2)
        assert results[0].chunk_id == "tlt-1", type(strategy).__name__


def test_metadata_filter(tmp_path):
    kb = make_kb(tmp_path)
    results = HybridSearch(kb).retrieve("effective duration", {"ticker": "SHY"}, k=3)
    assert [c.chunk_id for c in results] == ["shy-1"]
