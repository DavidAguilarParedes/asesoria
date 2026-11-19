from functools import partial
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel

from asesoria.application.retrieval import decorators as deco
from asesoria.application.retrieval.knowledge_base import KnowledgeBase
from asesoria.application.retrieval.strategies import (
    HybridSearchStrategy,
    SemanticSearchStrategy,
    SparseSearchStrategy,
)
from asesoria.config import Settings
from asesoria.domain.models import SourceDoc
from asesoria.domain.ports import RetrievalStrategy, VectorStore
from asesoria.infrastructure import downloader, policies
from asesoria.infrastructure.chunking.recursive import RecursiveChunker
from asesoria.infrastructure.embeddings.bm25 import BM25Embedder
from asesoria.infrastructure.embeddings.cache_proxy import CachingEmbedder
from asesoria.infrastructure.embeddings.openai import OpenAIEmbedder
from asesoria.infrastructure.llm import LLM, CostTracker
from asesoria.infrastructure.loaders.factory import LoaderFactory
from asesoria.infrastructure.vectorstores.qdrant import QdrantStore

EMBEDDING_DIMS = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}
COSTS_LOG = Path("logs/costs.jsonl")


class RetrievalConfig(BaseModel):
    """Qué capas se apilan. La ablación compara distintas combinaciones."""

    mode: str = "hybrid"
    contextual: bool = False
    rewrite: bool = False
    hyde: bool = False
    decompose: bool = False
    rerank: bool = False
    repack: str | None = None  # None, "sides" o "compress"

    @property
    def label(self) -> str:
        parts = [self.mode]
        for name in ("contextual", "rewrite", "hyde", "decompose", "rerank"):
            if getattr(self, name):
                parts.append(name)
        if self.repack:
            parts.append(f"repack-{self.repack}")
        return "+".join(parts)


class Container:
    """Composition root: crea cada dependencia una sola vez y arma el pipeline."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.tracker = CostTracker(settings.max_usd_per_run)
        self._openai: OpenAI | None = None
        self._llm: LLM | None = None
        self._reranker = None
        self._kbs: dict[str, KnowledgeBase] = {}
        self._stores: dict[str, VectorStore] = {}

    # --- corpus ---

    def sources(self) -> list[SourceDoc]:
        return downloader.read_sources(self.settings.data_dir / "sources.yaml")

    def fetcher(self, force: bool = False):
        return partial(downloader.download, user_agent=self.settings.sec_user_agent, force=force)

    def corpus_files(self) -> list[tuple[SourceDoc, Path]]:
        raw = self.settings.data_dir / "raw"
        public = [(d, raw / f"{d.id}{d.extension}") for d in self.sources()]
        policy = policies.policy_docs(self.settings.data_dir / "policies")
        return public + [(d, Path(d.url)) for d in policy]

    loader_for = staticmethod(LoaderFactory.get)

    @staticmethod
    def chunker() -> RecursiveChunker:
        return RecursiveChunker(max_words=600, overlap_words=80)

    # --- clientes ---

    @property
    def openai(self) -> OpenAI:
        if self._openai is None:
            if not self.settings.openai_api_key:
                raise RuntimeError("Falta OPENAI_API_KEY en .env")
            self._openai = OpenAI(api_key=self.settings.openai_api_key.get_secret_value())
        return self._openai

    @property
    def llm(self) -> LLM:
        if self._llm is None:
            self._llm = LLM(self.openai, self.tracker, Path(".cache/llm.sqlite"))
        return self._llm

    @property
    def reranker(self):
        if self._reranker is None:
            from asesoria.infrastructure.rerankers.cross_encoder import CrossEncoderReranker

            self._reranker = CrossEncoderReranker()
        return self._reranker

    def collection(self, contextual: bool) -> str:
        return f"{self.settings.collection}_ctx" if contextual else self.settings.collection

    def store(self, contextual: bool = False) -> VectorStore:
        # Qdrant local admite una sola conexión por carpeta: se reutiliza
        name = self.collection(contextual)
        if name not in self._stores:
            if self._stores:
                client = next(iter(self._stores.values())).client
            else:
                client = None
            dim = EMBEDDING_DIMS[self.settings.openai_embedding_model]
            self._stores[name] = QdrantStore(self.settings.qdrant_path, name, dim, client=client)
        return self._stores[name]

    def knowledge_base(self, contextual: bool = False) -> KnowledgeBase:
        name = self.collection(contextual)
        if name not in self._kbs:
            dense = CachingEmbedder(
                OpenAIEmbedder(self.openai, self.settings.openai_embedding_model, self.tracker),
                cache_path=Path(".cache/embeddings.sqlite"),
                namespace=self.settings.openai_embedding_model,
            )
            store = self.store(contextual)
            sparse = BM25Embedder() if store.supports_sparse else None
            self._kbs[name] = KnowledgeBase(dense, store, sparse)
        return self._kbs[name]

    def contextualizer(self):
        from asesoria.infrastructure.query_llm import LLMContextualizer

        return LLMContextualizer(self.llm, self.settings.openai_fast_model)

    # --- pipeline de recuperación ---

    def retriever(self, cfg: RetrievalConfig) -> RetrievalStrategy:
        from asesoria.infrastructure import query_llm as q

        fast = self.settings.openai_fast_model
        kb = self.knowledge_base(cfg.contextual)
        base = {
            "dense": SemanticSearchStrategy,
            "sparse": SparseSearchStrategy,
            "hybrid": HybridSearchStrategy,
        }[cfg.mode](kb)

        # Mismo orden que el recap del curso: pre-retrieval, rerank y al final el repacking
        pipeline: RetrievalStrategy = base
        if cfg.rewrite:
            pipeline = deco.QueryRewritingDecorator(pipeline, q.LLMQueryRewriter(self.llm, fast))
        if cfg.hyde:
            pipeline = deco.HyDEDecorator(pipeline, q.LLMHyDE(self.llm, fast))
        if cfg.decompose:
            pipeline = deco.DecompositionDecorator(pipeline, q.LLMDecomposer(self.llm, fast))
        if cfg.rerank:
            pipeline = deco.RerankingDecorator(pipeline, self.reranker)
        if cfg.repack == "sides":
            pipeline = deco.SidesRepackDecorator(pipeline)
        elif cfg.repack == "compress":
            pipeline = deco.CompressionDecorator(pipeline, q.LLMCompressor(self.llm, fast))
        return pipeline

    # --- agente ---

    def clients(self):
        from asesoria.infrastructure.clients import JsonClientRepository

        return JsonClientRepository(self.settings.data_dir / "clientes.json")

    def rules(self):
        return policies.read_rules(self.settings.data_dir / "policies")

    def agent_retrieval(self) -> RetrievalConfig:
        return RetrievalConfig(mode="hybrid", rerank=True)

    def record_agent_usage(self, usage: dict) -> None:
        self.tracker.add(
            self.settings.openai_chat_model,
            usage.get("input_token_count", 0),
            usage.get("openai.cached_input_tokens", 0),
            usage.get("output_token_count", 0),
        )

    def advisor(self, guard: bool = True, mcp=None):
        from agent_framework.openai import OpenAIChatClient

        from asesoria.application.advisor import AdvisorService
        from asesoria.application.tools import build_tools
        from asesoria.infrastructure.query_llm import LLMRelevanceChecker

        chat = OpenAIChatClient(
            model=self.settings.openai_chat_model,
            api_key=self.settings.openai_api_key.get_secret_value(),
        )
        from asesoria.infrastructure.mcp_alpaca import RISK

        rules = self.rules()
        tools = build_tools(
            retriever=self.retriever(self.agent_retrieval()),
            clients=self.clients(),
            rules=rules,
            min_score=self.settings.rag_min_score,
        )
        if mcp is not None:
            tools.append(mcp)
        relevance = (
            LLMRelevanceChecker(self.llm, self.settings.openai_fast_model) if guard else None
        )
        return AdvisorService(
            chat_client=chat,
            tools=tools,
            approved_symbols=rules.approved_symbols,
            relevance=relevance,
            trace_path=Path("logs/tool_calls.jsonl"),
            risk_by_tool=RISK,
            model_log_path=Path("logs/model_calls.jsonl"),
            on_usage=self.record_agent_usage,
            options={
                "reasoning": {"effort": self.settings.agent_reasoning_effort},
                "store": False,
                "allow_multiple_tool_calls": True,
            },
        )

    def alpaca(self):
        from asesoria.infrastructure.mcp_alpaca import alpaca_mcp

        return alpaca_mcp(self.settings)

    def close(self) -> None:
        for store in self._stores.values():
            store.client.close()
        self._stores.clear()

    def save_costs(self, command: str) -> str:
        self.tracker.save(COSTS_LOG, command)
        return self.tracker.summary()
