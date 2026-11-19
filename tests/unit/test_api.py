import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
