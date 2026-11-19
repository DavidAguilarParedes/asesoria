from asesoria.application.retrieval.decorators import (
    CompressionDecorator,
    DecompositionDecorator,
    HyDEDecorator,
    QueryRewritingDecorator,
    RerankingDecorator,
    RetrievalDecorator,
    SidesRepackDecorator,
)
from asesoria.domain.models import DocType, FilterSuggestion, ProcessedChunk
from asesoria.domain.ports import (
    ContextCompressor,
    HypotheticalDocGenerator,
    QueryDecomposer,
    QueryRewriter,
    Reranker,
    RetrievalStrategy,
)


def chunk(cid: str, text: str = "") -> ProcessedChunk:
    return ProcessedChunk(chunk_id=cid, content=text or cid, doc_id=cid, doc_type=DocType.GUIDE)


class SpyRetriever(RetrievalStrategy):
    """Devuelve chunks fijos y recuerda con qué lo llamaron."""

    def __init__(self, results_by_query: dict[str, list[str]] | None = None, default=None):
        self.results_by_query = results_by_query or {}
        self.default = default or ["a", "b", "c", "d", "e", "f", "g", "h"]
        self.calls: list[tuple[str, dict, int]] = []

    def retrieve_context(self, query, filters, k):
        self.calls.append((query, filters, k))
        ids = self.results_by_query.get(query, self.default)
        return [chunk(i) for i in ids[:k]]


def test_base_decorator_only_delegates():
    spy = SpyRetriever()
    assert [c.chunk_id for c in RetrievalDecorator(spy).retrieve_context("q", {}, 2)] == ["a", "b"]


def test_rewriting_uses_new_query_and_explicit_filters_win():
    class Rewriter(QueryRewriter):
        def rewrite(self, query):
            return FilterSuggestion(
                rewritten_query="tlt duration", ticker="TLT", doc_type="fact_sheet"
            )

    spy = SpyRetriever()
    QueryRewritingDecorator(spy, Rewriter()).retrieve_context("duración?", {"ticker": "AGG"}, 3)
    query, filters, _ = spy.calls[0]
    assert query == "tlt duration"
    assert filters["ticker"] == "AGG"
    assert filters["doc_type"] == "fact_sheet"


def test_hyde_searches_with_hypothetical_document():
    class Gen(HypotheticalDocGenerator):
        def generate(self, query):
            return "hypothetical answer"

    spy = SpyRetriever()
    HyDEDecorator(spy, Gen()).retrieve_context("question", {}, 3)
    assert spy.calls[0][0] == "hypothetical answer"


def test_decomposition_interleaves_and_deduplicates():
    class Splitter(QueryDecomposer):
        def decompose(self, query):
            return ["msft risks", "nvda risks"]

    spy = SpyRetriever({"msft risks": ["m1", "m2", "x"], "nvda risks": ["n1", "x", "n2"]})
    results = DecompositionDecorator(spy, Splitter()).retrieve_context("msft and nvda", {}, 4)
    assert [c.chunk_id for c in results] == ["m1", "n1", "m2", "x"]


def test_reranking_asks_for_more_candidates_and_reorders():
    class LengthReranker(Reranker):
        def score(self, query, texts):
            return [float(len(t)) for t in texts]

    spy = SpyRetriever(default=["a", "bbbb", "cc", "ddd"])
    results = RerankingDecorator(spy, LengthReranker(), candidates_factor=4).retrieve_context(
        "q", {}, 2
    )
    assert spy.calls[0][2] == 8
    assert [c.chunk_id for c in results] == ["bbbb", "ddd"]
    assert results[0].rerank_score == 4.0


def test_sides_repack_puts_best_at_both_ends():
    spy = SpyRetriever(default=["1", "2", "3", "4", "5"])
    results = SidesRepackDecorator(spy).retrieve_context("q", {}, 5)
    assert [c.chunk_id for c in results] == ["1", "3", "5", "4", "2"]


def test_compression_drops_irrelevant_chunks():
    class Compressor(ContextCompressor):
        def extract(self, query, text):
            return None if text == "b" else f"solo {text}"

    spy = SpyRetriever(default=["a", "b", "c"])
    results = CompressionDecorator(spy, Compressor()).retrieve_context("q", {}, 3)
    assert [c.content for c in results] == ["solo a", "solo c"]


def test_decorators_stack_like_the_course_recap():
    class Gen(HypotheticalDocGenerator):
        def generate(self, query):
            return "hyde"

    class Same(Reranker):
        def score(self, query, texts):
            return [1.0] * len(texts)

    spy = SpyRetriever()
    pipeline = SidesRepackDecorator(RerankingDecorator(HyDEDecorator(spy, Gen()), Same()))
    results = pipeline.retrieve_context("q", {}, 3)
    assert len(results) == 3
    assert spy.calls[0][0] == "hyde"
    assert spy.calls[0][2] == 12


def test_rewriter_filters_are_validated_by_code():
    from asesoria.infrastructure.query_llm import validate_filters

    # Alias en español: "bonos largos" es TLT aunque el LLM no lo detecte
    fixed = validate_filters(
        "¿qué tan sensible a las tasas es el ETF de bonos largos?",
        FilterSuggestion(rewritten_query="long bond ETF rate sensitivity", doc_type="policy"),
    )
    assert fixed.ticker == "TLT"
    assert fixed.doc_type is None

    # Apple no tiene prospecto y la pregunta no pidió un tipo de documento
    apple = validate_filters(
        "¿Qué riesgos menciona Apple sobre IA?",
        FilterSuggestion(
            rewritten_query="Apple AI risks", ticker="AAPL", doc_type="summary_prospectus"
        ),
    )
    assert apple.ticker == "AAPL"
    assert apple.doc_type is None

    # Tipo pedido explícitamente y coherente con el instrumento
    explicit = validate_filters(
        "En el reporte anual de NVIDIA, ¿qué dice de China?",
        FilterSuggestion(rewritten_query="NVIDIA China", ticker="NVDA", doc_type="10-K"),
    )
    assert explicit.doc_type == "10-K"

    # Varios instrumentos: sin filtro de ticker
    multi = validate_filters(
        "¿MSFT o NVDA?", FilterSuggestion(rewritten_query="msft vs nvda", ticker="MSFT")
    )
    assert multi.ticker is None
