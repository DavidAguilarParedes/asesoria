import typer

app = typer.Typer(help="AsesorIA: agente asesor de inversiones (demo, no es asesoría real)")


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
