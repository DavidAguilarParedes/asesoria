import typer

app = typer.Typer(help="AsesorIA: agente asesor de inversiones (demo, no es asesoría real)")


def _container():
    from asesoria.bootstrap import Container
    from asesoria.config import get_settings

    return Container(get_settings())


@app.command()
def download(force: bool = False) -> None:
    """Descarga los documentos públicos del corpus a data/raw/."""
    from asesoria.application.ingest import download_corpus

    c = _container()
    sources = c.sources()
    report = download_corpus(sources, c.fetcher(force), c.settings.data_dir / "raw")

    typer.echo(f"Descargados: {len(report.ok)}/{len(sources)}")
    for doc in report.manual:
        typer.echo(f"Manual: guarda {doc.url} como data/raw/{doc.id}{doc.extension}")
    for doc_id, error in report.failed.items():
        typer.echo(f"Error en {doc_id}: {error}")


@app.command()
def ingest(contextual: bool = False) -> None:
    """Carga, chunkea e indexa el corpus. Con --contextual agrega Contextual Retrieval."""
    from asesoria.application.ingest import add_context, load_units

    c = _container()
    files = c.corpus_files()
    missing = [str(p) for _, p in files if not p.exists()]
    if missing:
        typer.echo("Faltan archivos, corre primero `asesoria download`:\n" + "\n".join(missing))
        raise typer.Exit(1)

    units = load_units(files, c.loader_for)
    chunks = c.chunker().split(units)
    try:
        if contextual:
            chunks = add_context(chunks, units, c.contextualizer())
        store = c.store(contextual)
        store.reset()
        kb = c.knowledge_base(contextual)
        kb.index(chunks)
    finally:
        typer.echo(f"Costo LLM: {c.save_costs('ingest' + (' --contextual' if contextual else ''))}")

    typer.echo(
        f"Indexados {len(chunks)} chunks de {len(files)} documentos en {c.collection(contextual)}."
    )
    typer.echo(f"Embeddings: {kb.dense.misses} nuevos, {kb.dense.hits} desde caché.")


@app.command()
def search(
    query: str,
    ticker: str | None = None,
    doc_type: str | None = None,
    k: int = 5,
    mode: str = "hybrid",
    contextual: bool = False,
    rewrite: bool = False,
    hyde: bool = False,
    decompose: bool = False,
    rerank: bool = False,
    repack: str | None = None,
) -> None:
    """Busca en la base de conocimiento, con las capas que se elijan."""
    from asesoria.bootstrap import RetrievalConfig

    c = _container()
    cfg = RetrievalConfig(
        mode=mode,
        contextual=contextual,
        rewrite=rewrite,
        hyde=hyde,
        decompose=decompose,
        rerank=rerank,
        repack=repack,
    )
    try:
        results = c.retriever(cfg).retrieve_context(
            query, {"ticker": ticker, "doc_type": doc_type}, k
        )
    finally:
        cost = c.save_costs(f"search {cfg.label}")
        c.close()

    typer.echo(f"Pipeline: {cfg.label}")
    for i, chunk in enumerate(results, start=1):
        score = chunk.rerank_score if chunk.rerank_score is not None else chunk.score
        preview = chunk.content[:160].replace("\n", " ")
        typer.echo(f"{i}. [{score:.3f}] {chunk.chunk_id} · {chunk.section}\n   {preview}…")
    typer.echo(f"Costo LLM: {cost}")


def _print_reply(reply, show_tools: bool) -> None:
    if show_tools:
        for call in reply.tool_calls:
            args = ", ".join(f"{k}={v!r}" for k, v in call.arguments.items() if v is not None)
            typer.secho(f"  · {call.tool}({args}) [{call.ms} ms]", fg="cyan")
    if reply.blocked:
        typer.secho("  (bloqueado por el guardrail de relevancia)", fg="yellow")
    typer.echo(f"\nAsesorIA: {reply.text}\n")


@app.command()
def ask(message: str, client: str | None = "c-002", tools: bool = True) -> None:
    """Hace una sola pregunta al agente asesor."""
    import asyncio

    c = _container()
    advisor = c.advisor()
    session_id = advisor.start_session(client)
    try:
        reply = asyncio.run(advisor.ask(session_id, message))
        _print_reply(reply, tools)
    finally:
        typer.echo(f"Costo: {c.save_costs('ask')}")
        c.close()


@app.command()
def chat(client: str | None = "c-002", tools: bool = True) -> None:
    """Conversación con el agente en la terminal. Escribe 'salir' para terminar."""
    import asyncio

    c = _container()
    advisor = c.advisor()
    session_id = advisor.start_session(client)
    typer.echo(f"Sesión {session_id} · cliente {client}. Escribe 'salir' para terminar.")
    loop = asyncio.new_event_loop()
    try:
        while True:
            message = typer.prompt("Tú")
            if message.strip().lower() in {"salir", "exit", "quit"}:
                break
            _print_reply(loop.run_until_complete(advisor.ask(session_id, message)), tools)
    finally:
        loop.close()
        typer.echo(f"Costo de la sesión: {c.save_costs('chat')}")
        c.close()


@app.command()
def costs() -> None:
    """Muestra el gasto acumulado registrado en logs/costs.jsonl."""
    import json

    from asesoria.bootstrap import COSTS_LOG

    if not COSTS_LOG.exists():
        typer.echo("Todavía no hay gastos registrados.")
        return
    rows = [json.loads(line) for line in COSTS_LOG.read_text().splitlines() if line]
    total = sum(r["usd"] for r in rows)
    typer.echo(f"{len(rows)} comandos · {sum(r['calls'] for r in rows)} llamadas · USD {total:.4f}")


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
