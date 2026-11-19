import json
from pathlib import Path

import pytest

from asesoria.application.tools import build_tools
from asesoria.domain import finance
from asesoria.domain.models import ClientProfile, DocType, ProcessedChunk, RiskProfile
from asesoria.domain.ports import ClientRepository, RetrievalStrategy
from asesoria.infrastructure.policies import read_rules

RULES = read_rules(Path("data/policies"))


class FakeRetriever(RetrievalStrategy):
    def __init__(self, scores):
        self.scores = scores
        self.last_filters = None

    def retrieve_context(self, query, filters, k):
        self.last_filters = filters
        return [
            ProcessedChunk(
                chunk_id=f"c{i}",
                content="palabra " * 300,
                doc_id="nvda-10k-2026",
                doc_type=DocType.TEN_K,
                section="Item 1A · Risk Factors",
                rerank_score=s,
            )
            for i, s in enumerate(self.scores)
        ]


class FakeClients(ClientRepository):
    def get(self, client_id):
        if client_id != "c-002":
            return None
        return ClientProfile(
            client_id="c-002",
            name="Moderado",
            risk_profile=RiskProfile.MODERATE,
            portfolio_value_usd=10_000,
            horizon_years=5,
        )


def tools_by_name(scores=(1.0, -5.0)):
    retriever = FakeRetriever(list(scores))
    tools = build_tools(retriever, FakeClients(), RULES, min_score=-2.0)
    return {t.name: t for t in tools}, retriever


def call(tool, **kwargs):
    return json.loads(tool.func(**kwargs))


def test_search_keeps_only_results_above_threshold_and_truncates():
    tools, _ = tools_by_name()
    out = call(tools["buscar_documentos"], consulta="risks", ticker="nvda")
    assert [r["citation_id"] for r in out["resultados"]] == ["c0"]
    assert out["resultados"][0]["cita"] == "nvda-10k-2026, Item 1A · Risk Factors"
    assert len(out["resultados"][0]["texto"].split()) <= 181


def test_search_without_evidence_tells_agent_to_abstain():
    tools, _ = tools_by_name(scores=(-4.0, -6.0))
    out = call(tools["buscar_documentos"], consulta="anything")
    assert out["sin_evidencia"] is True
    assert "no tienes información suficiente" in out["hint"]


def test_search_rejects_symbol_outside_universe_without_searching():
    tools, retriever = tools_by_name()
    out = call(tools["buscar_documentos"], consulta="risks", ticker="TSLA")
    assert "universo aprobado" in out["error"]
    assert retriever.last_filters is None


def test_profile_includes_limits_per_symbol():
    tools, _ = tools_by_name()
    out = call(tools["perfil_cliente"], client_id="c-002")
    assert out["limite_por_instrumento"]["NVDA"] == "10%"
    assert out["limite_por_instrumento"]["TLT"] == "20%"
    assert out["no_aptos"] == []


def test_suitability_tool_returns_reason_and_max_allowed():
    tools, _ = tools_by_name()
    out = call(
        tools["validar_idoneidad"], client_id="c-002", simbolo="NVDA", cantidad=20, precio=150
    )
    assert out["approved"] is False
    assert out["reason"] == "EXCEDE_LIMITE_DE_CONCENTRACION"
    assert out["max_allowed_usd"] == 1000
    assert out["costo_estimado_usd"] == 3000


def test_calculator_reports_missing_data_instead_of_crashing():
    tools, _ = tools_by_name()
    assert (
        call(tools["calculadora_financiera"], operacion="costo_orden", cantidad=5, precio=10)[
            "resultado"
        ]
        == 50
    )
    assert "error" in call(tools["calculadora_financiera"], operacion="costo_orden", cantidad=5)


def test_finance_functions():
    assert finance.portfolio_pct(3000, 10_000) == 30
    assert finance.max_amount(10_000, 10) == 1000
    assert finance.max_shares(1000, 150) == 6
    assert finance.pct_return(100, 110) == 10
    assert finance.cagr(100, 121, 2) == 10
    assert finance.allocation(10_000, {"AGG": 60, "IVV": 40}) == {"AGG": 6000, "IVV": 4000}
    with pytest.raises(ValueError):
        finance.allocation(100, {"AGG": 50})
