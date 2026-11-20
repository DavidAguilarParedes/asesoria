import asyncio
import json
import re
from collections import defaultdict
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from asesoria.application.advisor import AdvisorReply
from asesoria.infrastructure.llm import BudgetExceeded

STATIC = Path(__file__).parent / "static"
RESULTS = Path("results")
DATA = Path("data")


def _local_file(doc_id: str) -> Path | None:
    """Archivo descargado (data/raw) o política interna (data/policies) del documento."""
    for folder in (DATA / "raw", DATA / "policies"):
        for path in sorted(folder.glob(f"{doc_id}.*")):
            return path
    return None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    client_id: str | None = None


class ApproveRequest(BaseModel):
    session_id: str
    approval_id: str
    approved: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    # En los tests el asesor ya viene armado
    if getattr(app.state, "advisor", None) is not None:
        yield
        return

    from asesoria.bootstrap import Container
    from asesoria.config import get_settings
    from asesoria.infrastructure.observability import setup_tracing

    settings = get_settings()
    setup_tracing(settings)
    c = Container(settings)
    async with AsyncExitStack() as stack:
        # El servidor de Alpaca se abre una vez y lo comparten todas las sesiones
        mcp = await stack.enter_async_context(c.alpaca()) if settings.api_use_mcp else None
        app.state.advisor = c.advisor(mcp=mcp)
        app.state.clients = c.clients()
        # Los chunks indexados se leen una vez para la pestaña Documentos (son pocos)
        app.state.chunks = c.store().payloads()
        try:
            yield
        finally:
            c.save_costs("serve")
            c.close()


def _natural(chunk_id: str) -> list:
    # Ordena "p2" antes que "p10": separa los números del texto
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", chunk_id)]


def create_app(advisor=None, clients=None, chunks=None) -> FastAPI:
    app = FastAPI(title="AsesorIA", lifespan=lifespan)
    app.state.advisor = advisor
    app.state.clients = clients
    app.state.chunks = chunks or []
    # Evita que dos requests de la misma sesión corran a la vez (p. ej. doble clic en aprobar)
    locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def advisor_of(request: Request):
        return request.app.state.advisor

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/clients")
    def list_clients(request: Request) -> list[dict]:
        repo = request.app.state.clients
        return [c.model_dump(mode="json") for c in repo.all()] if repo else []

    # --- Documentos del corpus, tal como los ve el agente (chunks indexados) ---

    def chunks_of(request: Request, doc_id: str) -> list[dict]:
        rows = [c for c in request.app.state.chunks if c["doc_id"] == doc_id]
        if not rows:
            raise HTTPException(404, f"El documento {doc_id} no existe")
        return sorted(rows, key=lambda c: _natural(c["chunk_id"]))

    @app.get("/documents")
    def list_documents(request: Request) -> list[dict]:
        docs: dict[str, dict] = {}
        for c in request.app.state.chunks:
            doc = docs.setdefault(
                c["doc_id"],
                {
                    "doc_id": c["doc_id"],
                    "doc_type": c["doc_type"],
                    "ticker": c.get("ticker"),
                    "source_url": c.get("source_url"),
                    "chunks": 0,
                },
            )
            doc["chunks"] += 1
        return sorted(docs.values(), key=lambda d: (d["doc_type"], d["doc_id"]))

    @app.get("/documents/{doc_id}")
    def get_document(doc_id: str, request: Request) -> dict:
        rows = chunks_of(request, doc_id)
        first = rows[0]
        return {
            "doc_id": doc_id,
            "doc_type": first["doc_type"],
            "ticker": first.get("ticker"),
            "source_url": first.get("source_url"),
            "has_file": _local_file(doc_id) is not None,
            "chunks": [
                {k: c.get(k) for k in ("chunk_id", "section", "page", "as_of", "content")}
                for c in rows
            ],
        }

    @app.get("/documents/{doc_id}/file", include_in_schema=False)
    def document_file(doc_id: str, request: Request):
        chunks_of(request, doc_id)  # solo se sirven documentos que existen en el índice
        path = _local_file(doc_id)
        if path is None:
            raise HTTPException(404, f"No se encontró el archivo de {doc_id}")
        media = "text/plain; charset=utf-8" if path.suffix == ".md" else None
        return FileResponse(path, media_type=media, content_disposition_type="inline")

    # --- Resultados de la evaluación (los genera `asesoria eval` y `asesoria ablation`) ---

    def read_json(name: str):
        path = RESULTS / name
        if not path.exists():
            raise HTTPException(404, f"Todavía no existe {path}; corre la evaluación primero")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/config")
    def config() -> dict:
        from asesoria.config import get_settings

        settings = get_settings()
        from asesoria.infrastructure.observability import experiment_id

        if not settings.mlflow_tracking_uri:
            return {"mlflow_ui_url": None, "mlflow_experiment_id": None}
        return {"mlflow_ui_url": settings.mlflow_ui_url, "mlflow_experiment_id": experiment_id()}

    @app.get("/eval")
    def evaluation() -> dict:
        return read_json("eval.json")

    @app.get("/eval/cases/{case_id}")
    def evaluation_case(case_id: str) -> dict:
        from evaluator.dataset import load_golden

        case = next((c for c in load_golden() if c.id == case_id), None)
        row = next((r for r in read_json("eval.json")["cases"] if r["case_id"] == case_id), None)
        run = next((r for r in read_json("eval_runs.json") if r["case_id"] == case_id), None)
        if case is None or row is None or run is None:
            raise HTTPException(404, f"El caso {case_id} no existe")
        calls = [
            {"tool": c["tool"], "arguments": c["arguments"], "result": c["result"][:600]}
            for c in run["calls"]
        ]
        return {
            "case": case.model_dump(),
            "scores": row,
            "response": run["response"],
            "rejection_reply": run["rejection_reply"],
            "calls": calls,
        }

    @app.get("/ablation")
    def ablation() -> dict:
        return read_json("ablation.json")

    @app.get("/analysis")
    def analysis() -> dict:
        path = RESULTS / "analisis.md"
        if not path.exists():
            raise HTTPException(404, "Todavía no existe el análisis")
        return {"markdown": path.read_text(encoding="utf-8")}

    @app.post("/chat")
    async def chat(body: ChatRequest, request: Request) -> AdvisorReply:
        advisor = advisor_of(request)
        session_id = body.session_id
        if session_id is None:
            repo = request.app.state.clients
            if body.client_id and repo and repo.get(body.client_id) is None:
                raise HTTPException(404, f"El cliente {body.client_id} no existe")
            session_id = advisor.start_session(body.client_id)
        elif advisor.get_state(session_id) is None:
            raise HTTPException(404, f"La sesión {session_id} no existe")
        async with locks[session_id]:
            try:
                return await advisor.ask(session_id, body.message)
            except BudgetExceeded as e:
                raise HTTPException(503, str(e)) from e

    @app.post("/chat/approve")
    async def approve(body: ApproveRequest, request: Request) -> AdvisorReply:
        advisor = advisor_of(request)
        if advisor.get_state(body.session_id) is None:
            raise HTTPException(404, f"La sesión {body.session_id} no existe")
        async with locks[body.session_id]:
            try:
                return await advisor.approve(body.session_id, body.approval_id, body.approved)
            except KeyError as e:
                raise HTTPException(404, str(e.args[0])) from e
            except BudgetExceeded as e:
                raise HTTPException(503, str(e)) from e

    return app


app = create_app()
