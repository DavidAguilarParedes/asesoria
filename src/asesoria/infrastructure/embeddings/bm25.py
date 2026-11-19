from fastembed import SparseTextEmbedding

from asesoria.domain.models import SparseVector
from asesoria.domain.ports import SparseEmbedder


class BM25Embedder(SparseEmbedder):
    """Vectores dispersos BM25. Qdrant aplica el IDF al buscar."""

    def __init__(self, model_name: str = "Qdrant/bm25"):
        self.model = SparseTextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]) -> list[SparseVector]:
        return [
            SparseVector(indices=e.indices.tolist(), values=e.values.tolist())
            for e in self.model.embed(texts)
        ]

    def embed_query(self, text: str) -> SparseVector:
        e = next(iter(self.model.query_embed(text)))
        return SparseVector(indices=e.indices.tolist(), values=e.values.tolist())
