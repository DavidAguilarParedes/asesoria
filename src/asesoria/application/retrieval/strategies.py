from asesoria.application.retrieval.knowledge_base import KnowledgeBase
from asesoria.domain.models import ProcessedChunk
from asesoria.domain.ports import RetrievalStrategy


class SemanticSearchStrategy(RetrievalStrategy):
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def retrieve_context(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]:
        return self.kb.dense_search(query, filters, k)


class SparseSearchStrategy(RetrievalStrategy):
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def retrieve_context(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]:
        return self.kb.sparse_search(query, filters, k)


class HybridSearchStrategy(RetrievalStrategy):
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def retrieve_context(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]:
        return self.kb.hybrid_search(query, filters, k)
