from asesoria.domain.models import ProcessedChunk, SparseVector
from asesoria.domain.ports import Embedder, Sparse, SparseEmbedder, VectorStore

# Campos que no se guardan como metadatos
NOT_PAYLOAD = {"dense_vector", "sparse_vector", "score", "rerank_score"}


def _to_primitive(vector: SparseVector) -> Sparse:
    return vector.indices, vector.values


class KnowledgeBase:
    """Abstracción del Bridge (el VectorStoreService del profesor).

    Es la única que conoce ProcessedChunk: serializa antes de guardar y rehidrata al buscar.
    """

    def __init__(self, dense: Embedder, store: VectorStore, sparse: SparseEmbedder | None = None):
        self.dense = dense
        self.sparse = sparse if store.supports_sparse else None
        self.store = store

    def index(self, chunks: list[ProcessedChunk]) -> None:
        dense = self.dense.embed_chunks(chunks)
        sparse = None
        if self.sparse:
            sparse = [_to_primitive(v) for v in self.sparse.embed_chunks(chunks)]
        self.store.index(
            ids=[c.chunk_id for c in chunks],
            dense=dense,
            sparse=sparse,
            payloads=[c.model_dump(mode="json", exclude=NOT_PAYLOAD) for c in chunks],
        )

    @staticmethod
    def _rehydrate(rows: list[dict]) -> list[ProcessedChunk]:
        return [ProcessedChunk(**row) for row in rows]

    def _sparse_query(self, query: str) -> Sparse:
        if not self.sparse:
            raise NotImplementedError("El vector store configurado no soporta búsqueda sparse")
        return _to_primitive(self.sparse.embed_query(query))

    def dense_search(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]:
        rows = self.store.search_dense(self.dense.embed_query(query), filters, k)
        return self._rehydrate(rows)

    def sparse_search(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]:
        return self._rehydrate(self.store.search_sparse(self._sparse_query(query), filters, k))

    def hybrid_search(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]:
        dense = self.dense.embed_query(query)
        rows = self.store.search_hybrid(dense, self._sparse_query(query), filters, k)
        return self._rehydrate(rows)
