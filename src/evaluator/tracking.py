"""Registro de experimentos en MLflow (opcional).

Cada corrida de la evaluación y cada configuración de la ablación queda como un run con
sus parámetros, métricas y archivos, para compararlas en la interfaz de MLflow.
Si MLFLOW_TRACKING_URI no está configurado, no se hace nada.
"""

from pathlib import Path


def _clean(name: str) -> str:
    # MLflow no acepta "@" en los nombres de las métricas
    return name.replace("@", "_at_")


def log_run(
    uri: str | None,
    experiment: str,
    run_name: str,
    params: dict,
    metrics: dict,
    artifacts: list[Path] = (),
    log=print,
) -> None:
    if not uri:
        return
    import mlflow

    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name=run_name):
        mlflow.log_params({k: str(v) for k, v in params.items()})
        numbers = {_clean(k): v for k, v in metrics.items() if isinstance(v, int | float)}
        mlflow.log_metrics(numbers)
        for path in artifacts:
            if path.exists():
                mlflow.log_artifact(str(path))
    log(f"Registrado en MLflow: {experiment} / {run_name}")
