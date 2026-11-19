import uuid
from pathlib import Path

from qdrant_client import QdrantClient, models

from asesoria.domain.models import ProcessedChunk, SparseVector
from asesoria.domain.ports import VectorStore

DENSE = "dense"
SPARSE = "bm25"
PAYLOAD_EXCLUDE = {"dense_vector", "sparse_vector", "score", "rerank_score"}


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def _filter(filters: dict) -> models.Filter | None:
    conditions = [
        models.FieldCondition(key=key, match=models.MatchValue(value=value))
        for key, value in filters.items()
        if value is not None
    ]
    return models.Filter(must=conditions) if conditions else None


def _sparse(vector: SparseVector) -> models.SparseVector:
    return models.SparseVector(indices=vector.indices, values=vector.values)


class QdrantStore(VectorStore):
    def __init__(self, path: Path, collection: str, dim: int):
        self.client = QdrantClient(path=str(path))
        self.collection = collection
        self.dim = dim

    def reset(self) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection,
            vectors_config={
                DENSE: models.VectorParams(size=self.dim, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )

    def index(self, chunks: list[ProcessedChunk]) -> None:
        points = [
            models.PointStruct(
                id=_point_id(c.chunk_id),
                vector={DENSE: c.dense_vector, SPARSE: _sparse(c.sparse_vector)},
                payload=c.model_dump(mode="json", exclude=PAYLOAD_EXCLUDE),
            )
            for c in chunks
        ]
        self.client.upload_points(self.collection, points=points, batch_size=128)

    def _to_chunks(self, points) -> list[ProcessedChunk]:
        return [ProcessedChunk(**p.payload, score=p.score) for p in points]

    def search_dense(self, vector, filters, k):
        res = self.client.query_points(
            self.collection, query=vector, using=DENSE, query_filter=_filter(filters), limit=k
        )
        return self._to_chunks(res.points)

    def search_sparse(self, vector, filters, k):
        res = self.client.query_points(
            self.collection,
            query=_sparse(vector),
            using=SPARSE,
            query_filter=_filter(filters),
            limit=k,
        )
        return self._to_chunks(res.points)

    def search_hybrid(self, dense, sparse, filters, k):
        flt = _filter(filters)
        res = self.client.query_points(
            self.collection,
            prefetch=[
                models.Prefetch(query=dense, using=DENSE, filter=flt, limit=k * 4),
                models.Prefetch(query=_sparse(sparse), using=SPARSE, filter=flt, limit=k * 4),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=k,
        )
        return self._to_chunks(res.points)
