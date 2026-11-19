from asesoria.domain.models import ProcessedChunk
from asesoria.domain.ports import (
    ContextCompressor,
    HypotheticalDocGenerator,
    QueryDecomposer,
    QueryRewriter,
    Reranker,
    RetrievalStrategy,
)


class RetrievalDecorator(RetrievalStrategy):
    """Base de los decorators: cumple la interfaz y por defecto solo delega."""

    def __init__(self, wrapped: RetrievalStrategy):
        self._wrapped = wrapped

    def retrieve_context(self, query: str, filters: dict, k: int) -> list[ProcessedChunk]:
        return self._wrapped.retrieve_context(query, filters, k)


# --- Pre-retrieval ---


class QueryRewritingDecorator(RetrievalDecorator):
    """Reescribe la pregunta y sugiere filtros. Los filtros explícitos tienen prioridad."""

    def __init__(self, wrapped: RetrievalStrategy, rewriter: QueryRewriter):
        super().__init__(wrapped)
        self._rewriter = rewriter

    def retrieve_context(self, query, filters, k):
        suggestion = self._rewriter.rewrite(query)
        suggested = {"ticker": suggestion.ticker, "doc_type": suggestion.doc_type}
        explicit = {key: value for key, value in filters.items() if value is not None}
        combined = {**suggested, **explicit}
        return self._wrapped.retrieve_context(suggestion.rewritten_query, combined, k)


class HyDEDecorator(RetrievalDecorator):
    """Busca con una respuesta hipotética en vez de la pregunta."""

    def __init__(self, wrapped: RetrievalStrategy, generator: HypotheticalDocGenerator):
        super().__init__(wrapped)
        self._generator = generator

    def retrieve_context(self, query, filters, k):
        return self._wrapped.retrieve_context(self._generator.generate(query), filters, k)


class DecompositionDecorator(RetrievalDecorator):
    """Divide preguntas compuestas y combina los resultados de cada sub-pregunta."""

    def __init__(self, wrapped: RetrievalStrategy, decomposer: QueryDecomposer):
        super().__init__(wrapped)
        self._decomposer = decomposer

    def retrieve_context(self, query, filters, k):
        sub_queries = self._decomposer.decompose(query) or [query]
        if len(sub_queries) == 1:
            return self._wrapped.retrieve_context(sub_queries[0], filters, k)

        per_query = [self._wrapped.retrieve_context(q, filters, k) for q in sub_queries]
        # Se intercalan para que cada sub-pregunta aporte sus mejores resultados
        merged: dict[str, ProcessedChunk] = {}
        for rank in range(k):
            for results in per_query:
                if rank < len(results) and results[rank].chunk_id not in merged:
                    merged[results[rank].chunk_id] = results[rank]
        return list(merged.values())[:k]


# --- Post-retrieval ---


class RerankingDecorator(RetrievalDecorator):
    """Pide más candidatos al componente envuelto y los reordena con un cross-encoder."""

    def __init__(self, wrapped: RetrievalStrategy, reranker: Reranker, candidates_factor: int = 4):
        super().__init__(wrapped)
        self._reranker = reranker
        self._factor = candidates_factor

    def retrieve_context(self, query, filters, k):
        candidates = self._wrapped.retrieve_context(query, filters, k * self._factor)
        if not candidates:
            return []
        scores = self._reranker.score(query, [c.content for c in candidates])
        scored = [
            c.model_copy(update={"rerank_score": s})
            for c, s in zip(candidates, scores, strict=True)
        ]
        scored.sort(key=lambda c: c.rerank_score, reverse=True)
        return scored[:k]


class SidesRepackDecorator(RetrievalDecorator):
    """Pone los mejores chunks al inicio y al final (efecto "lost in the middle")."""

    def retrieve_context(self, query, filters, k):
        chunks = self._wrapped.retrieve_context(query, filters, k)
        front, back = [], []
        for i, chunk in enumerate(chunks):
            (front if i % 2 == 0 else back).append(chunk)
        return front + back[::-1]


class CompressionDecorator(RetrievalDecorator):
    """Repacking por compresión: deja solo las oraciones relevantes de cada chunk."""

    def __init__(self, wrapped: RetrievalStrategy, compressor: ContextCompressor):
        super().__init__(wrapped)
        self._compressor = compressor

    def retrieve_context(self, query, filters, k):
        out = []
        for chunk in self._wrapped.retrieve_context(query, filters, k):
            extracted = self._compressor.extract(query, chunk.content)
            if extracted:
                out.append(chunk.model_copy(update={"content": extracted}))
        return out
