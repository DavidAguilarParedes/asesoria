"""Agente asesor con Microsoft Agent Framework."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from agent_framework import Agent, AgentSession, Message
from pydantic import BaseModel

from asesoria.application.middleware import (
    ModelCall,
    ModelTimingMiddleware,
    OrderGuardMiddleware,
    ToolCall,
    ToolTraceMiddleware,
)
from asesoria.application.order_gate import OrderGate
from asesoria.application.prompts import SYSTEM_PROMPT, session_context
from asesoria.domain.ports import RelevanceChecker

OFF_TOPIC_REPLY = (
    "Solo puedo ayudarte con consultas de inversión sobre los instrumentos aprobados, "
    "el perfil del cliente o las políticas internas."
)

UsageCallback = Callable[[dict], None]


class PendingOrder(BaseModel):
    approval_id: str
    tool: str
    arguments: dict
    resumen: dict = {}


class AdvisorReply(BaseModel):
    session_id: str
    text: str
    status: str = "ok"  # ok | blocked | pending_approval
    pending: list[PendingOrder] = []
    tool_calls: list[ToolCall] = []
    model_calls: list[ModelCall] = []
    usage: dict = {}


@dataclass
class SessionState:
    session: AgentSession
    client_id: str | None
    gate: OrderGate
    pending: dict = field(default_factory=dict)  # approval_id -> request de MAF
    turns: int = 0


def _arguments(function_call) -> dict:
    args = getattr(function_call, "arguments", None) or {}
    if isinstance(args, str):
        try:
            return json.loads(args)
        except json.JSONDecodeError:
            return {}
    return dict(args)


@dataclass
class AdvisorService:
    chat_client: object
    tools: list
    approved_symbols: set[str]
    relevance: RelevanceChecker | None = None
    trace_path: Path | None = None
    risk_by_tool: dict[str, str] = field(default_factory=dict)
    model_log_path: Path | None = None
    on_usage: UsageCallback | None = None
    options: dict = field(default_factory=dict)
    _sessions: dict[str, SessionState] = field(default_factory=dict)

    def start_session(self, client_id: str | None = None, session_id: str | None = None) -> str:
        session = AgentSession(session_id=session_id)
        gate = OrderGate(approved_symbols=self.approved_symbols)
        self._sessions[session.session_id] = SessionState(session, client_id, gate)
        return session.session_id

    def get_state(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def _state(self, session_id: str) -> SessionState:
        state = self._sessions.get(session_id)
        if state is None:
            raise KeyError(f"La sesión {session_id} no existe")
        return state

    def _agent(self, state: SessionState, middleware: list) -> Agent:
        instructions = f"{SYSTEM_PROMPT}\n\n{session_context(state.client_id)}"
        return Agent(
            self.chat_client,
            instructions,
            name="asesoria",
            tools=self.tools,
            middleware=middleware,
            default_options=self.options,
        )

    async def _run(self, session_id: str, message) -> AdvisorReply:
        state = self._state(session_id)
        tool_calls: list[ToolCall] = []
        model_calls: list[ModelCall] = []
        middleware = [
            # El trace va primero para registrar también las órdenes bloqueadas
            ToolTraceMiddleware(
                self.trace_path, risk_by_tool=self.risk_by_tool, sink=tool_calls.append
            ),
            OrderGuardMiddleware(state.gate),
            ModelTimingMiddleware(model_calls.append, self.model_log_path),
        ]
        agent = self._agent(state, middleware)
        response = await agent.run(message, session=state.session)
        state.turns += 1
        self._track(response)

        # Las órdenes inválidas se rechazan solas; el usuario solo confirma las válidas
        rejections = []
        for request in response.user_input_requests:
            args = _arguments(request.function_call)
            decision = state.gate.check(args)
            if decision.allowed:
                state.pending[request.id] = request
            else:
                rejections.append(request.to_function_approval_response(False))
        if rejections and not state.pending:
            return await self._run(session_id, Message("user", rejections))

        pending = self._pending(state)
        return AdvisorReply(
            session_id=session_id,
            text=response.text,
            status="pending_approval" if pending else "ok",
            pending=pending,
            tool_calls=tool_calls,
            model_calls=model_calls,
            usage=dict(getattr(response, "usage_details", None) or {}),
        )

    @staticmethod
    def _pending(state: SessionState) -> list[PendingOrder]:
        orders = []
        for approval_id, req in state.pending.items():
            args = _arguments(req.function_call)
            orders.append(
                PendingOrder(
                    approval_id=approval_id,
                    tool=req.function_call.name,
                    arguments=args,
                    resumen=state.gate.summary(args),
                )
            )
        return orders

    def _track(self, response) -> None:
        usage = dict(getattr(response, "usage_details", None) or {})
        if self.on_usage and usage:
            self.on_usage(usage)

    async def ask(self, session_id: str, message: str) -> AdvisorReply:
        state = self._state(session_id)
        if state.pending:
            return AdvisorReply(
                session_id=session_id,
                text="Hay una orden esperando tu confirmación. Apruébala o recházala primero.",
                status="pending_approval",
                pending=self._pending(state),
            )
        if self.relevance:
            verdict = self.relevance.check(message)
            if not verdict.on_topic:
                return AdvisorReply(session_id=session_id, text=OFF_TOPIC_REPLY, status="blocked")
        return await self._run(session_id, message)

    async def approve(self, session_id: str, approval_id: str, approved: bool) -> AdvisorReply:
        state = self._state(session_id)
        request = state.pending.pop(approval_id, None)
        if request is None:
            raise KeyError(f"No hay una orden pendiente con id {approval_id}")
        contents = [request.to_function_approval_response(approved)]
        if not approved:
            # Sin este aviso el modelo a veces vuelve a ofrecer la misma orden
            contents.append("Cancelo la orden. Confírmame en una línea que no se ejecutó.")
        return await self._run(session_id, Message("user", contents))
