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
        return ".pdf" if self.url.lower().endswith(".pdf") else ".html"


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
    dense_vector: list[float] | None = None
    score: float | None = None
    rerank_score: float | None = None


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
