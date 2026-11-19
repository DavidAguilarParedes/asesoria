from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DocType(StrEnum):
    TEN_K = "10-K"
    FACT_SHEET = "fact_sheet"
    PROSPECTUS = "summary_prospectus"
    GUIDE = "guide"
    POLICY = "policy"


class RiskProfile(StrEnum):
    CONSERVATIVE = "conservador"
    MODERATE = "moderado"
    AGGRESSIVE = "agresivo"


class SourceDoc(BaseModel):
    id: str
    doc_type: DocType
    url: str
    ticker: str | None = None
    manual: bool = False

    @property
    def extension(self) -> str:
        for ext in (".pdf", ".md"):
            if self.url.lower().endswith(ext):
                return ext
        return ".html"


class SparseVector(BaseModel):
    indices: list[int]
    values: list[float]


class ProcessedChunk(BaseModel):
    chunk_id: str
    content: str
    doc_id: str
    doc_type: DocType
    ticker: str | None = None
    section: str | None = None
    page: int | None = None
    as_of: date | None = None
    source_url: str | None = None
    context: str | None = None
    parent_id: str | None = None
    dense_vector: list[float] | None = None
    sparse_vector: SparseVector | None = None
    score: float | None = None
    rerank_score: float | None = None

    @property
    def embedding_text(self) -> str:
        return f"{self.context}\n{self.content}" if self.context else self.content


class Citation(BaseModel):
    model_config = ConfigDict(frozen=True)

    citation_id: str
    label: str
    source_url: str | None = None


class ClientProfile(BaseModel):
    client_id: str
    name: str
    risk_profile: RiskProfile
    portfolio_value_usd: float = Field(gt=0)
    horizon_years: int = Field(gt=0)


class Order(BaseModel):
    symbol: str
    qty: float = Field(gt=0)
    side: str = "buy"
    est_price_usd: float | None = None

    @property
    def est_cost_usd(self) -> float | None:
        if self.est_price_usd is None:
            return None
        return round(self.qty * self.est_price_usd, 2)


class FilterSuggestion(BaseModel):
    """Salida estructurada del query rewriting (clase 6 del curso)."""

    rewritten_query: str
    ticker: str | None = None
    doc_type: DocType | None = None
