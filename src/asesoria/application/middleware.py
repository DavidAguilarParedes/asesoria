import json
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from agent_framework import ChatMiddleware, FunctionMiddleware, MiddlewareTermination
from pydantic import BaseModel


class ToolCall(BaseModel):
    at: str
    session_id: str | None
    tool: str
    riesgo: str | None
    arguments: dict
    result: str
    ms: int
    ok: bool


def _result_text(result) -> str:
    if result is None:
        return ""
    if isinstance(result, list):
        return " ".join(str(getattr(item, "text", item)) for item in result)
    return str(result)


class ToolTraceMiddleware(FunctionMiddleware):
    """Registra cada tool invocada con su entrada, salida y duración."""

    def __init__(
        self,
        log_path: Path | None = None,
        max_chars: int = 2000,
        risk_by_tool: dict[str, str] | None = None,
        sink: Callable[[ToolCall], None] | None = None,
    ):
        self.log_path = log_path
        self.max_chars = max_chars
        self.risk_by_tool = risk_by_tool or {}
        # El framework puede copiar el middleware; el sink es una referencia que sobrevive
        self.sink = sink

    async def process(self, context, call_next) -> None:
        args = context.arguments
        arguments = args.model_dump() if hasattr(args, "model_dump") else dict(args)
        started = time.perf_counter()
        ok = True
        try:
            await call_next()
        except Exception:
            ok = False
            raise
        finally:
            props = getattr(context.function, "additional_properties", None) or {}
            session = getattr(context, "session", None)
            call = ToolCall(
                at=datetime.now().isoformat(timespec="seconds"),
                session_id=getattr(session, "session_id", None),
                tool=context.function.name,
                riesgo=props.get("riesgo") or self.risk_by_tool.get(context.function.name, "bajo"),
                arguments=arguments,
                result=_result_text(context.result)[: self.max_chars],
                ms=int((time.perf_counter() - started) * 1000),
                ok=ok,
            )
            if self.sink:
                self.sink(call)
            if self.log_path:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(call.model_dump(), ensure_ascii=False) + "\n")


class OrderGuardMiddleware(FunctionMiddleware):
    """Bloquea en código cualquier orden que no cumpla las reglas, aunque el usuario la apruebe."""

    def __init__(self, gate):
        self.gate = gate

    async def process(self, context, call_next) -> None:
        args = context.arguments
        arguments = args.model_dump() if hasattr(args, "model_dump") else dict(args)
        name = context.function.name

        if name == "place_stock_order":
            decision = self.gate.check(arguments)
            if not decision.allowed:
                context.result = json.dumps(
                    {"bloqueada": True, "motivo": decision.reason}, ensure_ascii=False
                )
                raise MiddlewareTermination()

        await call_next()

        if name == "validar_idoneidad":
            self.gate.record_validation(arguments, _result_text(context.result))


class ModelCall(BaseModel):
    at: str
    ms: int
    messages: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class ModelTimingMiddleware(ChatMiddleware):
    """Mide cada llamada al modelo: sirve para analizar latencia y costo."""

    def __init__(self, sink: Callable[[ModelCall], None], log_path: Path | None = None):
        self.sink = sink
        self.log_path = log_path

    async def process(self, context, call_next) -> None:
        started = time.perf_counter()
        await call_next()
        usage = getattr(context.result, "usage_details", None) or {}
        call = ModelCall(
            at=datetime.now().isoformat(timespec="seconds"),
            ms=int((time.perf_counter() - started) * 1000),
            messages=len(context.messages),
            input_tokens=usage.get("input_token_count"),
            output_tokens=usage.get("output_token_count"),
        )
        self.sink(call)
        if self.log_path:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(call.model_dump()) + "\n")
