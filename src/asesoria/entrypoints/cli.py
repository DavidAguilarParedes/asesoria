import typer

app = typer.Typer(help="AsesorIA: agente asesor de inversiones (demo, no es asesoría real)")


@app.command()
def download(force: bool = False) -> None:
    """Descarga los documentos públicos del corpus a data/raw/."""
    from asesoria import bootstrap
    from asesoria.application.ingest import download_corpus
    from asesoria.config import get_settings

    settings = get_settings()
    sources = bootstrap.load_sources(settings)
    fetch = bootstrap.make_fetcher(settings, force)
    report = download_corpus(sources, fetch, settings.data_dir / "raw")

    typer.echo(f"Descargados: {len(report.ok)}/{len(sources)}")
    for doc in report.manual:
        typer.echo(f"Manual: guarda {doc.url} como data/raw/{doc.id}{doc.extension}")
    for doc_id, error in report.failed.items():
        typer.echo(f"Error en {doc_id}: {error}")


@app.command()
def ingest(contextual: bool = False) -> None:
    """Descarga e indexa el corpus."""
    typer.echo(f"ingest (contextual={contextual}): pendiente")


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Levanta la API."""
    import uvicorn

    uvicorn.run("asesoria.entrypoints.api:app", host=host, port=port)


@app.command("eval")
def evaluate() -> None:
    """Corre el agente evaluador."""
    typer.echo("eval: pendiente")


@app.command()
def ablation() -> None:
    """Compara configuraciones del RAG."""
    typer.echo("ablation: pendiente")


if __name__ == "__main__":
    app()
