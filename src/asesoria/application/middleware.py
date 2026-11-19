import json
import time
from datetime import datetime
from pathlib import Path

from agent_framework import FunctionMiddleware
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

    def __init__(self, log_path: Path | None = None, max_chars: int = 2000):
        self.log_path = log_path
        self.max_chars = max_chars
        self.calls: list[ToolCall] = []

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
                riesgo=props.get("riesgo"),
                arguments=arguments,
                result=_result_text(context.result)[: self.max_chars],
                ms=int((time.perf_counter() - started) * 1000),
                ok=ok,
            )
            self.calls.append(call)
            if self.log_path:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(call.model_dump(), ensure_ascii=False) + "\n")
