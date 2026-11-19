from functools import partial
from pathlib import Path

from openai import OpenAI

from asesoria.application.retrieval.knowledge_base import KnowledgeBase
from asesoria.application.retrieval.strategies import DenseSearch, HybridSearch, SparseSearch
from asesoria.config import Settings
from asesoria.domain.models import SourceDoc
from asesoria.domain.ports import RetrievalStrategy
from asesoria.infrastructure import downloader, policies
from asesoria.infrastructure.chunking.recursive import RecursiveChunker
from asesoria.infrastructure.embeddings.bm25 import BM25Embedder
from asesoria.infrastructure.embeddings.cache_proxy import CachingEmbedder
from asesoria.infrastructure.embeddings.openai import OpenAIEmbedder
from asesoria.infrastructure.loaders.factory import LoaderFactory
from asesoria.infrastructure.vectorstores.qdrant import QdrantStore

EMBEDDING_DIMS = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}


def load_sources(settings: Settings) -> list[SourceDoc]:
    return downloader.read_sources(settings.data_dir / "sources.yaml")


def make_fetcher(settings: Settings, force: bool = False):
    return partial(downloader.download, user_agent=settings.sec_user_agent, force=force)


def corpus_files(settings: Settings) -> list[tuple[SourceDoc, Path]]:
    raw = settings.data_dir / "raw"
    public = [(d, raw / f"{d.id}{d.extension}") for d in load_sources(settings)]
    internal = [(d, Path(d.url)) for d in policies.policy_docs(settings.data_dir / "policies")]
    return public + internal


def make_chunker() -> RecursiveChunker:
    return RecursiveChunker(max_words=600, overlap_words=80)


def make_openai(settings: Settings) -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("Falta OPENAI_API_KEY en .env")
    return OpenAI(api_key=settings.openai_api_key.get_secret_value())


def make_store(settings: Settings) -> QdrantStore:
    dim = EMBEDDING_DIMS[settings.openai_embedding_model]
    return QdrantStore(settings.qdrant_path, settings.collection, dim)


def make_knowledge_base(settings: Settings, store: QdrantStore | None = None) -> KnowledgeBase:
    dense = CachingEmbedder(
        OpenAIEmbedder(make_openai(settings), settings.openai_embedding_model),
        cache_path=Path(".cache/embeddings.sqlite"),
        namespace=settings.openai_embedding_model,
    )
    return KnowledgeBase(dense, BM25Embedder(), store or make_store(settings))


def make_retriever(kb: KnowledgeBase, mode: str = "hybrid") -> RetrievalStrategy:
    strategies = {"dense": DenseSearch, "sparse": SparseSearch, "hybrid": HybridSearch}
    return strategies[mode](kb)


loader_for = LoaderFactory.get
