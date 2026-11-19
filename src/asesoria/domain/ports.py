from abc import ABC, abstractmethod
from pathlib import Path

from asesoria.domain.models import ProcessedChunk, SourceDoc, SparseVector


class Loader(ABC):
    @abstractmethod
    def load(self, doc: SourceDoc, path: Path) -> list[ProcessedChunk]: ...


class ChunkingStrategy(ABC):
    @abstractmethod
    def split(self, chunks: list[ProcessedChunk]) -> list[ProcessedChunk]: ...


class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SparseEmbedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[SparseVector]: ...


class VectorStore(ABC):
    """Implementación de la base vectorial (lado "cómo" del Bridge)."""

    @abstractmethod
    def index(self, chunks: list[ProcessedChunk]) -> None: ...

    @abstractmethod
    def search_dense(self, vector: list[float], filters: dict, k: int) -> list[ProcessedChunk]: ...

    @abstractmethod
    def search_sparse(
        self, vector: SparseVector, filters: dict, k: int
    ) -> list[ProcessedChunk]: ...

    @abstractmethod
    def search_hybrid(
        self, dense: list[float], sparse: SparseVector, filters: dict, k: int
    ) -> list[ProcessedChunk]: ...


class RetrievalStrategy(ABC):
    @abstractmethod
    def retrieve(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]: ...
