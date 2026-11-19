from abc import ABC, abstractmethod
from pathlib import Path

from asesoria.domain.models import ProcessedChunk, SourceDoc


class Loader(ABC):
    @abstractmethod
    def load(self, doc: SourceDoc, path: Path) -> list[ProcessedChunk]: ...


class ChunkingStrategy(ABC):
    @abstractmethod
    def split(self, chunks: list[ProcessedChunk]) -> list[ProcessedChunk]: ...


class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorStore(ABC):
    @abstractmethod
    def index(self, chunks: list[ProcessedChunk]) -> None: ...

    @abstractmethod
    def search(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]: ...


class RetrievalStrategy(ABC):
    @abstractmethod
    def retrieve(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]: ...
