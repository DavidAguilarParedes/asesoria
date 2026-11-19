import uuid
from pathlib import Path

from qdrant_client import QdrantClient, models

from asesoria.domain.ports import Sparse, VectorStore

DENSE = "dense"
SPARSE = "bm25"


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def _filter(filters: dict) -> models.Filter | None:
    conditions = [
        models.FieldCondition(key=key, match=models.MatchValue(value=value))
        for key, value in filters.items()
        if value is not None
    ]
    return models.Filter(must=conditions) if conditions else None


def _sparse(vector: Sparse) -> models.SparseVector:
    indices, values = vector
    return models.SparseVector(indices=indices, values=values)


def _rows(points) -> list[dict]:
    return [{**p.payload, "score": p.score} for p in points]


class QdrantStore(VectorStore):
    supports_sparse = True

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

    def index(self, ids, dense, sparse, payloads) -> None:
        sparse = sparse or [None] * len(ids)
        points = []
        for chunk_id, d, s, payload in zip(ids, dense, sparse, payloads, strict=True):
            vector = {DENSE: d}
            if s is not None:
                vector[SPARSE] = _sparse(s)
            points.append(
                models.PointStruct(id=_point_id(chunk_id), vector=vector, payload=payload)
            )
        self.client.upload_points(self.collection, points=points, batch_size=128)

    def search_dense(self, vector, filters, k):
        res = self.client.query_points(
            self.collection, query=vector, using=DENSE, query_filter=_filter(filters), limit=k
        )
        return _rows(res.points)

    def search_sparse(self, vector, filters, k):
        res = self.client.query_points(
            self.collection,
            query=_sparse(vector),
            using=SPARSE,
            query_filter=_filter(filters),
            limit=k,
        )
        return _rows(res.points)

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
        return _rows(res.points)
