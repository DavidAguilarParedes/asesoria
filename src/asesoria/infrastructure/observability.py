"""Trazas del agente en MLflow (opcional).

Agent Framework emite trazas OpenTelemetry de cada conversación: el agente, cada llamada
al modelo y cada tool con su entrada y salida. Aquí se envían al servidor de MLflow.
Si MLFLOW_TRACKING_URI no está configurado, no se hace nada.
"""

from asesoria.config import Settings

_configured = False


def setup_tracing(settings: Settings, experiment: str = "asesoria-chat") -> bool:
    global _configured
    if _configured or not settings.mlflow_tracking_uri:
        return _configured

    import mlflow
    from agent_framework.observability import configure_otel_providers
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    uri = settings.mlflow_tracking_uri.rstrip("/")
    mlflow.set_tracking_uri(uri)
    experiment_id = mlflow.set_experiment(experiment).experiment_id
    # MLflow recibe trazas OTLP en /v1/traces; el header indica en qué experimento guardarlas
    exporter = OTLPSpanExporter(
        endpoint=f"{uri}/v1/traces", headers={"x-mlflow-experiment-id": experiment_id}
    )
    configure_otel_providers(
        service_name="asesoria", exporters=[exporter], enable_sensitive_data=True
    )
    _configured = True
    return True


def flush() -> None:
    """Envía las trazas pendientes (al terminar un comando de la CLI)."""
    if _configured:
        from opentelemetry import trace

        trace.get_tracer_provider().force_flush()
