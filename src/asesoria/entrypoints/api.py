import asyncio
from collections import defaultdict
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from asesoria.application.advisor import AdvisorReply
from asesoria.infrastructure.llm import BudgetExceeded

STATIC = Path(__file__).parent / "static"


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

    settings = get_settings()
    c = Container(settings)
    async with AsyncExitStack() as stack:
        # El servidor de Alpaca se abre una vez y lo comparten todas las sesiones
        mcp = await stack.enter_async_context(c.alpaca()) if settings.api_use_mcp else None
        app.state.advisor = c.advisor(mcp=mcp)
        app.state.clients = c.clients()
        try:
            yield
        finally:
            c.save_costs("serve")
            c.close()


def create_app(advisor=None, clients=None) -> FastAPI:
    app = FastAPI(title="AsesorIA", lifespan=lifespan)
    app.state.advisor = advisor
    app.state.clients = clients
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
