from abc import ABC, abstractmethod
from pathlib import Path

from asesoria.domain.models import FilterSuggestion, ProcessedChunk, SourceDoc, SparseVector


class Loader(ABC):
    @abstractmethod
    def load(self, doc: SourceDoc, path: Path) -> list[ProcessedChunk]: ...


class ChunkingStrategy(ABC):
    @abstractmethod
    def split(self, chunks: list[ProcessedChunk]) -> list[ProcessedChunk]: ...


class Embedder(ABC):
    """Adapter: traduce los chunks Pydantic al formato que espera cada modelo."""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    def embed_chunks(self, chunks: list[ProcessedChunk]) -> list[list[float]]:
        return self.embed_texts([c.embedding_text for c in chunks])

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]


class SparseEmbedder(ABC):
    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[SparseVector]: ...

    def embed_chunks(self, chunks: list[ProcessedChunk]) -> list[SparseVector]:
        return self.embed_texts([c.embedding_text for c in chunks])

    def embed_query(self, query: str) -> SparseVector:
        return self.embed_texts([query])[0]


# Vector disperso en formato primitivo: (índices, valores)
Sparse = tuple[list[int], list[float]]


class VectorStore(ABC):
    """Lado "cómo" del Bridge. Solo recibe y devuelve datos primitivos, no conoce Pydantic."""

    supports_sparse: bool = False

    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def index(
        self,
        ids: list[str],
        dense: list[list[float]],
        sparse: list[Sparse] | None,
        payloads: list[dict],
    ) -> None: ...

    @abstractmethod
    def search_dense(self, vector: list[float], filters: dict, k: int) -> list[dict]: ...

    def search_sparse(self, vector: Sparse, filters: dict, k: int) -> list[dict]:
        raise NotImplementedError(f"{type(self).__name__} no soporta búsqueda sparse")

    def search_hybrid(
        self, dense: list[float], sparse: Sparse, filters: dict, k: int
    ) -> list[dict]:
        raise NotImplementedError(f"{type(self).__name__} no soporta búsqueda híbrida")


class RetrievalStrategy(ABC):
    @abstractmethod
    def retrieve_context(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]: ...


class Reranker(ABC):
    @abstractmethod
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class QueryRewriter(ABC):
    @abstractmethod
    def rewrite(self, query: str) -> FilterSuggestion: ...


class HypotheticalDocGenerator(ABC):
    @abstractmethod
    def generate(self, query: str) -> str: ...


class QueryDecomposer(ABC):
    @abstractmethod
    def decompose(self, query: str) -> list[str]: ...


class ContextCompressor(ABC):
    @abstractmethod
    def extract(self, query: str, text: str) -> str | None: ...


class ChunkContextualizer(ABC):
    @abstractmethod
    def situate(self, document: str, chunk: ProcessedChunk) -> str: ...
