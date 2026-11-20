"""Trazas del agente en MLflow (opcional).

Cada turno del chat es una traza: la raíz tiene la pregunta y la respuesta, y adentro
están las llamadas al modelo y a las tools. Si MLFLOW_TRACKING_URI no está configurado,
no se hace nada.
"""

import json
from contextlib import contextmanager

from asesoria.config import Settings

_configured = False
_experiment_id: str | None = None
_turns: set[int] = set()  # trace_id de los turnos del chat

ESTADOS = {"ok": "respondió", "pending_approval": "orden pendiente", "blocked": "bloqueada"}


def setup_tracing(settings: Settings, experiment: str = "asesoria-chat") -> bool:
    global _configured, _experiment_id
    if _configured or not settings.mlflow_tracking_uri:
        return _configured

    import mlflow
    from agent_framework.observability import configure_otel_providers
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    uri = settings.mlflow_tracking_uri.rstrip("/")
    mlflow.set_tracking_uri(uri)
    _experiment_id = mlflow.set_experiment(experiment).experiment_id
    # MLflow recibe trazas OTLP en /v1/traces; el header indica en qué experimento guardarlas
    exporter = OTLPSpanExporter(
        endpoint=f"{uri}/v1/traces", headers={"x-mlflow-experiment-id": _experiment_id}
    )
    configure_otel_providers(
        service_name="asesoria", exporters=[_only_turns(exporter)], enable_sensitive_data=True
    )
    _configured = True
    return True


def _only_turns(exporter):
    # FastAPI y el cliente MCP también crean spans (GET /clients, pings...): se descartan
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

    class OnlyTurns(SpanExporter):
        def export(self, spans):
            keep = [s for s in spans if s.context.trace_id in _turns]
            if not keep:
                return SpanExportResult.SUCCESS
            return exporter.export(keep)

        def shutdown(self):
            exporter.shutdown()

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            return exporter.force_flush(timeout_millis)

    return OnlyTurns()


def experiment_id() -> str | None:
    return _experiment_id


def flush() -> None:
    """Envía las trazas pendientes (al terminar un comando de la CLI)."""
    if _configured:
        from opentelemetry import trace

        trace.get_tracer_provider().force_flush()


class TracedAdvisor:
    """El asesor, con cada pregunta y cada aprobación como una traza en MLflow."""

    def __init__(self, advisor):
        self._advisor = advisor

    def __getattr__(self, name):
        # start_session, get_state, etc. pasan directo al asesor
        return getattr(self._advisor, name)

    async def ask(self, session_id: str, message: str):
        with self._turn(session_id, "Pregunta", message) as span:
            reply = await self._advisor.ask(session_id, message)
            _finish(span, reply)
            return reply

    async def approve(self, session_id: str, approval_id: str, approved: bool):
        decision = "Aprobó la orden" if approved else "Rechazó la orden"
        with self._turn(session_id, "Aprobación", decision) as span:
            reply = await self._advisor.approve(session_id, approval_id, approved)
            if span is not None:
                span.set_attribute("mlflow.traceTag.decision", decision)
            _finish(span, reply)
            return reply

    @contextmanager
    def _turn(self, session_id: str, kind: str, message: str):
        if not _configured:
            yield None
            return

        from opentelemetry import context, trace

        state = self._advisor.get_state(session_id)
        client = (state.client_id if state else None) or "sin cliente"
        tracer = trace.get_tracer("asesoria")
        # Contexto vacío: la traza empieza aquí y no dentro de la petición HTTP
        with tracer.start_as_current_span("AsesorIA", context=context.Context()) as span:
            _turns.add(span.get_span_context().trace_id)
            span.set_attributes(
                {
                    # session.id agrupa los turnos en la vista Sessions de MLflow
                    "session.id": session_id,
                    "user.id": client,
                    "mlflow.spanType": json.dumps("AGENT"),
                    "mlflow.traceTag.mlflow.traceName": f"{kind} · {client}",
                    "mlflow.traceTag.cliente": client,
                    # Formato de chat de OpenAI: así MLflow muestra el texto en la lista
                    "mlflow.spanInputs": _dumps(
                        {"messages": [{"role": "user", "content": message}]}
                    ),
                }
            )
            yield span


def _finish(span, reply) -> None:
    """Guarda la respuesta final y las etiquetas del turno."""
    if span is None:
        return
    text = reply.text
    tools = [t.tool for t in reply.tool_calls]
    for order in reply.pending:
        r = order.resumen
        # La orden va primero para que se vea en la vista previa
        line = f"[Orden pendiente: comprar {r.get('cantidad')} {r.get('simbolo')}"
        text = f"{line} · costo estimado USD {r.get('costo_estimado_usd')}]\n\n{text}"
        tools.append(order.tool)
    tools = list(dict.fromkeys(tools))  # sin repetidos, en orden
    answer = {"choices": [{"message": {"role": "assistant", "content": text.strip()}}]}
    span.set_attributes(
        {
            "mlflow.spanOutputs": _dumps(answer),
            "mlflow.traceTag.estado": ESTADOS.get(reply.status, reply.status),
            "mlflow.traceTag.herramientas": ", ".join(tools) or "ninguna",
        }
    )


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)
