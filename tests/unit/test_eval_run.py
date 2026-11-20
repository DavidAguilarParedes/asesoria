import json

from asesoria.domain.models import DocType, ProcessedChunk
from evaluator.dataset import EvidenceRef, Expectation, ExpectedToolCall, GoldenCase
from evaluator.judge import conversation
from evaluator.run import (
    CaseRun,
    behavior_checks,
    expected_tool_calls,
    retrieval_rank,
    summarize,
)


def case(**kwargs):
    base = {"id": "c1", "type": "rag", "question": "q", "reference": "r"}
    return GoldenCase(**(base | kwargs))


def search(*ids):
    result = json.dumps({"resultados": [{"citation_id": i, "cita": i, "texto": "t"} for i in ids]})
    return {"tool": "buscar_documentos", "arguments": {"consulta": "x"}, "result": result}


def test_rank_usa_la_mejor_busqueda():
    chunks = {
        "x": ProcessedChunk(chunk_id="x", content="t", doc_id="otro", doc_type=DocType.GUIDE),
        "y": ProcessedChunk(
            chunk_id="y", content="t", doc_id="shy-factsheet", doc_type=DocType.FACT_SHEET
        ),
    }
    c = case(evidence=[[EvidenceRef(doc_id="shy-factsheet")]])
    run = CaseRun(case_id="c1", calls=[search("x"), search("x", "y")])
    assert retrieval_rank(run, c, chunks) == 2
    assert retrieval_rank(CaseRun(case_id="c1"), c, chunks) is None


def test_tools_esperadas_para_preguntas_de_documentos():
    c = case(
        evidence=[
            [EvidenceRef(doc_id="shy-factsheet")],
            [EvidenceRef(doc_id="politica-idoneidad")],
        ]
    )
    assert expected_tool_calls(c) == [
        {"name": "buscar_documentos", "args": {"ticker": "SHY"}},
        {"name": "buscar_documentos", "args": {"ticker": None}},
    ]


def test_checks_de_comportamiento():
    run = CaseRun(case_id="c1", calls=[{"tool": "perfil_cliente", "arguments": {}, "result": ""}])
    c = case(evidence=[[EvidenceRef(doc_id="politica-idoneidad")]])
    assert behavior_checks(run, c, None) == {"usa buscar_documentos": False}

    expect = Expectation(
        approval=True,
        executes=False,
        tool_calls=[ExpectedToolCall(name="validar_idoneidad", args={"simbolo": "AAPL"})],
    )
    order = case(type="behavior", expect=expect)
    run = CaseRun(
        case_id="c1",
        approval_requested=True,
        calls=[{"tool": "validar_idoneidad", "arguments": {}, "result": "{}"}],
    )
    assert all(behavior_checks(run, order, None).values())

    neg = case(type="negative", expect=Expectation(abstain=True))
    assert behavior_checks(CaseRun(case_id="c1"), neg, 1) == {"se abstiene": True}
    assert behavior_checks(CaseRun(case_id="c1"), neg, 0) == {"se abstiene": False}


def test_conversacion_incluye_tools_y_rechazo():
    calls = [{"tool": "validar_idoneidad", "arguments": {"simbolo": "AAPL"}, "result": "ok"}]
    messages = conversation("Compra AAPL", calls, "Orden propuesta", "Orden cancelada")
    kinds = [m.type for m in messages]
    assert kinds == ["human", "ai", "tool", "ai", "human", "ai"]
    assert messages[1].tool_calls[0].name == "validar_idoneidad"


def test_resumen():
    def row(hit, rank, faith, checks=()):
        metrics = {
            m: None for m in ["correctness", "goal_accuracy", "tool_call_accuracy", "guardrails"]
        }
        return {
            "hit": hit,
            "rank": rank,
            "faithfulness": faith,
            **metrics,
            "failed_checks": list(checks),
            "seconds": 10.0,
            "error": None,
        }

    s = summarize([row(True, 2, 1.0), row(False, None, 0.0), row(None, None, None)])
    assert s["hit@5"] == 0.5
    assert s["mrr@5"] == 0.25
    assert s["faithfulness"] == 0.5
    assert s["n_faithfulness"] == 2


def test_se_tapa_la_cuenta_de_alpaca():
    from evaluator.run import hide_account

    raw = '{"data": {"id": "abc-1111", "account_number": "PA123", "cash": "100000"}}'
    out = hide_account(raw)
    assert "PA123" not in out and "abc-1111" not in out
    assert '"cash": "100000"' in out
