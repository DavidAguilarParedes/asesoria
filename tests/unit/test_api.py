import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from asesoria.application import progress
from asesoria.application.advisor import AdvisorReply, PendingOrder
from asesoria.entrypoints.api import create_app
from asesoria.infrastructure.clients import JsonClientRepository
from asesoria.infrastructure.llm import BudgetExceeded


class FakeAdvisor:
    def __init__(self):
        self.sessions = {}
        self.fail_budget = False

    def start_session(self, client_id=None):
        sid = f"s{len(self.sessions) + 1}"
        self.sessions[sid] = {"client": client_id, "pending": set()}
        return sid

    def get_state(self, session_id):
        return self.sessions.get(session_id)

    async def ask(self, session_id, message):
        if self.fail_budget:
            raise BudgetExceeded("Se superó el tope")
        if "compra" in message:
            self.sessions[session_id]["pending"].add("a1")
            order = PendingOrder(approval_id="a1", tool="place_stock_order", arguments={})
            return AdvisorReply(
                session_id=session_id,
                text="Revisa la orden",
                status="pending_approval",
                pending=[order],
            )
        # Como el middleware real: avisa qué tool está usando
        progress.notify({"type": "tool", "id": 1, "tool": "perfil_cliente", "arguments": {}})
        progress.notify({"type": "tool_done", "id": 1, "ok": True})
        return AdvisorReply(session_id=session_id, text=f"eco: {message}")

    async def approve(self, session_id, approval_id, approved):
        pending = self.sessions[session_id]["pending"]
        if approval_id not in pending:
            raise KeyError(f"No hay una orden pendiente con id {approval_id}")
        pending.discard(approval_id)
        return AdvisorReply(session_id=session_id, text="ejecutada" if approved else "cancelada")


@pytest.fixture
def advisor():
    return FakeAdvisor()


@pytest.fixture
def api(advisor):
    clients = JsonClientRepository(Path("data/clientes.json"))
    with TestClient(create_app(advisor=advisor, clients=clients)) as client:
        yield client


def test_chat_crea_sesion_y_la_reutiliza(api, advisor):
    r = api.post("/chat", json={"message": "hola", "client_id": "c-002"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert advisor.sessions[sid]["client"] == "c-002"

    r = api.post("/chat", json={"message": "otra", "session_id": sid})
    assert r.json()["session_id"] == sid
    assert len(advisor.sessions) == 1


def test_sesion_o_cliente_inexistente_da_404(api):
    assert api.post("/chat", json={"message": "hola", "session_id": "nope"}).status_code == 404
    assert api.post("/chat", json={"message": "hola", "client_id": "c-999"}).status_code == 404


def test_mensaje_vacio_da_422(api):
    assert api.post("/chat", json={"message": ""}).status_code == 422


def test_flujo_de_aprobacion(api):
    r = api.post("/chat", json={"message": "compra 2 MSFT", "client_id": "c-003"}).json()
    assert r["status"] == "pending_approval"
    body = {"session_id": r["session_id"], "approval_id": "a1", "approved": False}

    r2 = api.post("/chat/approve", json=body)
    assert r2.status_code == 200
    assert r2.json()["text"] == "cancelada"

    # La misma orden no se puede decidir dos veces
    assert api.post("/chat/approve", json=body).status_code == 404


def test_chat_stream_envia_las_tools_y_luego_la_respuesta(api):
    r = api.post("/chat/stream", json={"message": "hola", "client_id": "c-002"})
    assert r.status_code == 200
    events = [json.loads(line) for line in r.text.splitlines()]
    assert [e["type"] for e in events] == ["tool", "tool_done", "reply"]
    assert events[0]["tool"] == "perfil_cliente"
    assert events[-1]["reply"]["text"] == "eco: hola"

    assert api.post("/chat/stream", json={"message": "x", "session_id": "nope"}).status_code == 404


def test_chat_stream_avisa_el_tope_de_gasto(api, advisor):
    advisor.fail_budget = True
    r = api.post("/chat/stream", json={"message": "hola"})
    assert json.loads(r.text.splitlines()[-1])["type"] == "error"


def test_tope_de_gasto_da_503(api, advisor):
    advisor.fail_budget = True
    r = api.post("/chat", json={"message": "hola"})
    assert r.status_code == 503


def test_clientes_y_pagina(api):
    ids = [c["client_id"] for c in api.get("/clients").json()]
    assert ids == ["c-001", "c-002", "c-003"]
    assert "AsesorIA" in api.get("/").text


def test_resultados_de_la_evaluacion(api, tmp_path, monkeypatch):
    import asesoria.entrypoints.api as module

    monkeypatch.setattr(module, "RESULTS", tmp_path)
    assert api.get("/eval").status_code == 404

    (tmp_path / "eval.json").write_text(
        json.dumps({"summary": {"total": {}}, "cases": [{"case_id": "pol-01", "hit": True}]})
    )
    (tmp_path / "eval_runs.json").write_text(
        json.dumps(
            [
                {
                    "case_id": "pol-01",
                    "response": "10%",
                    "rejection_reply": None,
                    "calls": [{"tool": "buscar_documentos", "arguments": {}, "result": "x"}],
                }
            ]
        )
    )
    assert api.get("/eval").json()["cases"][0]["case_id"] == "pol-01"
    detail = api.get("/eval/cases/pol-01").json()
    assert detail["response"] == "10%"
    assert detail["case"]["question"].startswith("¿Cuál es el máximo")
    assert api.get("/eval/cases/no-existe").status_code == 404


def _chunk(chunk_id, section, content="texto"):
    return {
        "chunk_id": chunk_id,
        "doc_id": "guia",
        "doc_type": "guide",
        "ticker": None,
        "section": section,
        "page": None,
        "as_of": None,
        "source_url": "https://example.com/guia",
        "content": content,
    }


def test_documentos(advisor, tmp_path, monkeypatch):
    import asesoria.entrypoints.api as module

    monkeypatch.setattr(module, "DATA", tmp_path)
    (tmp_path / "raw").mkdir()
    (tmp_path / "policies").mkdir()
    (tmp_path / "raw" / "guia.html").write_text("<p>hola</p>", encoding="utf-8")
    chunks = [_chunk("guia-p10", "B"), _chunk("guia-p2", "A")]
    with TestClient(create_app(advisor=advisor, chunks=chunks)) as api:
        docs = api.get("/documents").json()
        assert docs == [
            {
                "doc_id": "guia",
                "doc_type": "guide",
                "ticker": None,
                "source_url": "https://example.com/guia",
                "chunks": 2,
            }
        ]
        doc = api.get("/documents/guia").json()
        # "p2" va antes que "p10"
        assert [c["chunk_id"] for c in doc["chunks"]] == ["guia-p2", "guia-p10"]
        assert doc["has_file"] is True
        assert api.get("/documents/guia/file").text == "<p>hola</p>"
        assert api.get("/documents/otro").status_code == 404
        assert api.get("/documents/otro/file").status_code == 404


def test_ejemplo_grabado_se_repite_sin_llamar_al_agente(api, tmp_path, monkeypatch):
    from asesoria.entrypoints import examples

    monkeypatch.setattr(examples, "PATH", tmp_path / "ejemplos.json")
    tool = {"type": "tool", "id": 1, "tool": "perfil_cliente", "arguments": {}, "ms": 10}
    reply = AdvisorReply(session_id="vieja", text="grabada").model_dump()
    example = examples.Example(client_id="c-002", question="¿Hola?", events=[tool], reply=reply)
    examples.save([example])

    r = api.post("/chat/stream", json={"message": " ¿hola? ", "client_id": "c-002"})
    events = [json.loads(line) for line in r.text.splitlines()]
    assert [e["type"] for e in events] == ["tool", "reply"]
    last = events[-1]["reply"]
    assert last["text"] == "grabada" and last["cached"] is True
    assert last["session_id"] != "vieja"  # la sesión es nueva y real

    # En una conversación ya empezada la misma pregunta va en vivo
    r = api.post("/chat/stream", json={"message": "¿Hola?", "session_id": last["session_id"]})
    assert json.loads(r.text.splitlines()[-1])["reply"]["text"] == "eco: ¿Hola?"


class FakeJudge:
    model = "juez-de-prueba"

    def judge(self, question, answer, tool_calls):
        from asesoria.infrastructure.judge import Criterion, JudgeVerdict

        ok = Criterion(score=1, reason="bien")
        return JudgeVerdict(
            basado_en_fuentes=ok,
            resuelve_lo_pedido=ok,
            uso_de_herramientas=Criterion(score=0.5, reason=f"{len(tool_calls)} tools"),
            respeta_las_reglas=ok,
            veredicto="confiable",
        )


def test_juez_califica_una_respuesta(advisor):
    with TestClient(create_app(advisor=advisor, judge=FakeJudge())) as api:
        body = {"question": "¿Precio de MSFT?", "answer": "USD 498", "tool_calls": [{"tool": "x"}]}
        r = api.post("/judge", json=body).json()
        assert r["model"] == "juez-de-prueba"
        assert r["uso_de_herramientas"] == {"score": 0.5, "reason": "1 tools"}
        assert r["veredicto"] == "confiable"


def test_juez_no_disponible_da_503(api):
    assert api.post("/judge", json={"question": "a", "answer": "b"}).status_code == 503
