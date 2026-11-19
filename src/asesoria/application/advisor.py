"""Agente asesor con Microsoft Agent Framework."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from agent_framework import Agent, AgentSession
from pydantic import BaseModel

from asesoria.application.middleware import ToolCall, ToolTraceMiddleware
from asesoria.application.prompts import SYSTEM_PROMPT, session_context
from asesoria.domain.ports import RelevanceChecker

OFF_TOPIC_REPLY = (
    "Solo puedo ayudarte con consultas de inversión sobre los instrumentos aprobados, "
    "el perfil del cliente o las políticas internas."
)

UsageCallback = Callable[[dict], None]


class AdvisorReply(BaseModel):
    session_id: str
    text: str
    blocked: bool = False
    tool_calls: list[ToolCall] = []
    usage: dict = {}


@dataclass
class SessionState:
    session: AgentSession
    client_id: str | None
    turns: int = 0


@dataclass
class AdvisorService:
    chat_client: object
    tools: list
    relevance: RelevanceChecker | None = None
    trace_path: Path | None = None
    on_usage: UsageCallback | None = None
    options: dict = field(default_factory=dict)
    _sessions: dict[str, SessionState] = field(default_factory=dict)

    def _agent(self, client_id: str | None, middleware: list) -> Agent:
        instructions = f"{SYSTEM_PROMPT}\n\n{session_context(client_id)}"
        return Agent(
            self.chat_client,
            instructions,
            name="asesoria",
            tools=self.tools,
            middleware=middleware,
            default_options=self.options,
        )

    def start_session(self, client_id: str | None = None, session_id: str | None = None) -> str:
        session = AgentSession(session_id=session_id)
        self._sessions[session.session_id] = SessionState(session=session, client_id=client_id)
        return session.session_id

    def get_state(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    async def ask(self, session_id: str, message: str) -> AdvisorReply:
        state = self._sessions.get(session_id)
        if state is None:
            raise KeyError(f"La sesión {session_id} no existe")

        if self.relevance:
            verdict = self.relevance.check(message)
            if not verdict.on_topic:
                return AdvisorReply(session_id=session_id, text=OFF_TOPIC_REPLY, blocked=True)

        trace = ToolTraceMiddleware(self.trace_path)
        agent = self._agent(state.client_id, [trace])
        response = await agent.run(message, session=state.session)
        state.turns += 1

        usage = dict(getattr(response, "usage_details", None) or {})
        if self.on_usage and usage:
            self.on_usage(usage)
        return AdvisorReply(
            session_id=session_id, text=response.text, tool_calls=trace.calls, usage=usage
        )
