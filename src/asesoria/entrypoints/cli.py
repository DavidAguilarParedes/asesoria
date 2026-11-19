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
            typer.secho(f"  · {call.tool}({args}) [{call.ms} ms, riesgo {call.riesgo}]", fg="cyan")
    if show_tools and reply.model_calls:
        total = sum(m.ms for m in reply.model_calls) / 1000
        typer.secho(f"  · {len(reply.model_calls)} llamadas al modelo, {total:.1f} s", fg="cyan")
    if reply.status == "blocked":
        typer.secho("  (bloqueado por el guardrail de relevancia)", fg="yellow")
    typer.echo(f"\nAsesorIA: {reply.text}\n")
    for order in reply.pending:
        r = order.resumen
        lines = [
            f"Comprar {r.get('cantidad')} {r.get('simbolo')} (orden de mercado, {r.get('cuenta')})",
            f"Precio estimado: USD {r.get('precio_usd')}",
            f"Costo estimado: USD {r.get('costo_estimado_usd')}",
            f"Porcentaje del portafolio: {r.get('porcentaje_del_portafolio')}%",
            f"Idoneidad: {r.get('idoneidad')}",
        ]
        typer.secho("  ORDEN PENDIENTE DE CONFIRMACIÓN", fg="yellow", bold=True)
        for line in lines:
            typer.secho(f"    {line}", fg="yellow")


async def _session(client: str | None, use_mcp: bool):
    """Abre el MCP de Alpaca (si se pide) y devuelve el contenedor y el asesor."""
    from contextlib import AsyncExitStack

    c = _container()
    stack = AsyncExitStack()
    mcp = await stack.enter_async_context(c.alpaca()) if use_mcp else None
    advisor = c.advisor(mcp=mcp)
    return c, advisor, stack


@app.command()
def ask(message: str, client: str | None = "c-002", tools: bool = True, mcp: bool = True) -> None:
    """Hace una sola pregunta. Si el agente propone una orden, queda sin ejecutar."""
    import asyncio

    async def run():
        c, advisor, stack = await _session(client, mcp)
        try:
            session_id = advisor.start_session(client)
            reply = await advisor.ask(session_id, message)
            _print_reply(reply, tools)
            if reply.pending:
                typer.echo("(con `ask` las órdenes no se ejecutan; usa `chat` para confirmarlas)")
        finally:
            await stack.aclose()
            typer.echo(f"Costo: {c.save_costs('ask')}")
            c.close()

    asyncio.run(run())


@app.command()
def chat(client: str | None = "c-002", tools: bool = True, mcp: bool = True) -> None:
    """Conversación en la terminal. Escribe 'salir' para terminar."""
    import asyncio

    async def run():
        c, advisor, stack = await _session(client, mcp)
        session_id = advisor.start_session(client)
        typer.echo(f"Sesión {session_id} · cliente {client}. Escribe 'salir' para terminar.")
        try:
            while True:
                message = await asyncio.to_thread(typer.prompt, "Tú")
                if message.strip().lower() in {"salir", "exit", "quit"}:
                    break
                reply = await advisor.ask(session_id, message)
                _print_reply(reply, tools)
                while reply.pending:
                    order = reply.pending[0]
                    ok = await asyncio.to_thread(typer.confirm, "¿Confirmas la orden?")
                    reply = await advisor.approve(session_id, order.approval_id, ok)
                    _print_reply(reply, tools)
        finally:
            await stack.aclose()
            typer.echo(f"Costo de la sesión: {c.save_costs('chat')}")
            c.close()

    asyncio.run(run())


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
def serve(host: str = "0.0.0.0", port: int = 8000, mcp: bool = True) -> None:
    """Levanta la API y la página de demo en http://localhost:8000."""
    import os

    import uvicorn

    os.environ["API_USE_MCP"] = str(mcp).lower()

    uvicorn.run("asesoria.entrypoints.api:app", host=host, port=port)


@app.command("eval")
def evaluate() -> None:
    """Corre el agente evaluador."""
    typer.echo("eval: pendiente")


@app.command()
def ablation(only: str | None = None) -> None:
    """Compara configuraciones del RAG con el set de evaluación (results/ablation.*)."""
    from evaluator.ablation import main

    c = _container()
    try:
        main(c, only, log=typer.echo)
    finally:
        typer.echo(f"Costo: {c.save_costs('ablation')}")
        c.close()


@app.command("agent-queries")
def agent_queries() -> None:
    """Repite las búsquedas reales del agente en cada colección."""
    import asyncio

    from evaluator.agent_queries import main

    c = _container()
    try:
        asyncio.run(main(c, log=typer.echo))
    finally:
        typer.echo(f"Costo: {c.save_costs('agent-queries')}")
        c.close()


if __name__ == "__main__":
    app()
