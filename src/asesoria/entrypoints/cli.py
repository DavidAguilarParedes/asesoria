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
    """Carga, chunkea e indexa el corpus en Qdrant."""
    from asesoria import bootstrap
    from asesoria.application.ingest import build_chunks
    from asesoria.config import get_settings

    if contextual:
        typer.echo("El modo --contextual todavía no está implementado.")
        raise typer.Exit(1)

    settings = get_settings()
    files = bootstrap.corpus_files(settings)
    missing = [str(p) for _, p in files if not p.exists()]
    if missing:
        typer.echo("Faltan archivos, corre primero `asesoria download`:\n" + "\n".join(missing))
        raise typer.Exit(1)

    chunks = build_chunks(files, bootstrap.loader_for, bootstrap.make_chunker())
    store = bootstrap.make_store(settings)
    store.reset()
    kb = bootstrap.make_knowledge_base(settings, store)
    kb.index(chunks)
    typer.echo(f"Indexados {len(chunks)} chunks de {len(files)} documentos.")
    typer.echo(f"Embeddings: {kb.dense.misses} nuevos, {kb.dense.hits} desde caché.")


@app.command()
def search(
    query: str,
    ticker: str | None = None,
    doc_type: str | None = None,
    mode: str = "hybrid",
    k: int = 5,
) -> None:
    """Busca en la base de conocimiento (para probar a mano)."""
    from asesoria import bootstrap
    from asesoria.config import get_settings

    settings = get_settings()
    retriever = bootstrap.make_retriever(bootstrap.make_knowledge_base(settings), mode)
    results = retriever.retrieve(query, {"ticker": ticker, "doc_type": doc_type}, k)
    for i, c in enumerate(results, start=1):
        preview = c.content[:160].replace("\n", " ")
        typer.echo(f"{i}. [{c.score:.3f}] {c.chunk_id} · {c.section}\n   {preview}…")


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
