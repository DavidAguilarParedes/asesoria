from asesoria.domain.models import ProcessedChunk
from asesoria.domain.ports import Embedder, SparseEmbedder, VectorStore


class KnowledgeBase:
    """Abstracción del Bridge: conoce los chunks y los embedders, delega el guardado al store."""

    def __init__(self, dense: Embedder, sparse: SparseEmbedder, store: VectorStore):
        self.dense = dense
        self.sparse = sparse
        self.store = store

    def index(self, chunks: list[ProcessedChunk]) -> None:
        texts = [c.embedding_text for c in chunks]
        dense = self.dense.embed(texts)
        sparse = self.sparse.embed(texts)
        enriched = [
            c.model_copy(update={"dense_vector": d, "sparse_vector": s})
            for c, d, s in zip(chunks, dense, sparse, strict=True)
        ]
        self.store.index(enriched)

    def _sparse_query(self, query: str):
        embed_query = getattr(self.sparse, "embed_query", None)
        return embed_query(query) if embed_query else self.sparse.embed([query])[0]

    def dense_search(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]:
        return self.store.search_dense(self.dense.embed([query])[0], filters, k)

    def sparse_search(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]:
        return self.store.search_sparse(self._sparse_query(query), filters, k)

    def hybrid_search(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]:
        dense = self.dense.embed([query])[0]
        return self.store.search_hybrid(dense, self._sparse_query(query), filters, k)
