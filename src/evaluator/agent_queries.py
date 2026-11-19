"""Compara colecciones usando las búsquedas que escribe el agente de verdad.

1. El agente responde cada caso y se guardan sus llamadas a buscar_documentos.
2. Esas mismas búsquedas se repiten en cada configuración.
Así la única diferencia entre configuraciones es la recuperación.
"""

import json
from pathlib import Path

from asesoria.bootstrap import Container, RetrievalConfig
from evaluator.dataset import load_golden
from evaluator.metrics import first_relevant_rank, recall_at_k

QUERIES = Path("results/agent_queries.json")
K = 5

CONFIGS = [
    RetrievalConfig(mode="hybrid", rerank=True),
    RetrievalConfig(mode="hybrid", contextual=True, rerank=True),
    RetrievalConfig(mode="dense", contextual=True),
]


async def collect(container: Container, cases, log=print) -> dict:
    """Corre el agente (sin MCP) y devuelve {case_id: [búsquedas]}."""
    advisor = container.advisor(mcp=None)
    queries = {}
    for case in cases:
        session_id = advisor.start_session(case.client_id)
        reply = await advisor.ask(session_id, case.question)
        searches = [call.arguments for call in reply.tool_calls if call.tool == "buscar_documentos"]
        queries[case.id] = searches
        log(f"{case.id}: {len(searches)} búsquedas")
    return queries


def replay(container: Container, cfg: RetrievalConfig, cases, queries: dict) -> dict:
    retriever = container.retriever(cfg)
    hits, reciprocal, recall, no_search = 0, 0.0, 0.0, 0
    for case in cases:
        searches = queries.get(case.id, [])
        if not searches:
            no_search += 1
            continue
        # El agente ve los resultados de todas sus búsquedas: se juntan en orden
        chunks = []
        for args in searches:
            filters = {"ticker": args.get("ticker"), "doc_type": args.get("tipo_documento")}
            chunks += retriever.retrieve_context(args["consulta"], filters, K)
        # Para el rango se toma la mejor posición en cualquiera de las búsquedas
        ranks = []
        for i in range(0, len(chunks), K):
            rank = first_relevant_rank(chunks[i : i + K], case.evidence, K)
            if rank:
                ranks.append(rank)
        if ranks:
            hits += 1
            reciprocal += 1 / min(ranks)
        recall += recall_at_k(chunks, case.evidence, len(chunks))
    n = len(cases)
    return {
        "config": cfg.label,
        "cases": n,
        "hit@5": round(hits / n, 3),
        "mrr@5": round(reciprocal / n, 3),
        "recall": round(recall / n, 3),
        "sin_busqueda": no_search,
    }


async def main(container: Container, log=print) -> None:
    cases = [c for c in load_golden() if c.evidence]
    if QUERIES.exists():
        queries = json.loads(QUERIES.read_text())
        log(f"Uso las búsquedas guardadas en {QUERIES}")
    else:
        queries = await collect(container, cases, log)
        QUERIES.write_text(json.dumps(queries, indent=2, ensure_ascii=False))

    results = [replay(container, cfg, cases, queries) for cfg in CONFIGS]
    for r in results:
        log(
            f"{r['config']:<28} hit@5 {r['hit@5']:.2f}  mrr {r['mrr@5']:.2f}  "
            f"recall {r['recall']:.2f}  sin búsqueda {r['sin_busqueda']}"
        )
    Path("results/agent_queries_summary.json").write_text(json.dumps(results, indent=2))
