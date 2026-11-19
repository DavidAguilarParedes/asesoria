"""Nivel 1: compara configuraciones del RAG con el set de evaluación."""

import csv
import json
import time
from pathlib import Path

from pydantic import BaseModel

from asesoria.bootstrap import Container, RetrievalConfig
from asesoria.domain.models import ProcessedChunk
from evaluator.dataset import GoldenCase, load_golden
from evaluator.metrics import first_relevant_rank, matches, percentile, recall_at_k

K = 5
OUT = Path("results")

# Cada fila agrega una pieza a la anterior, como en la escalera del plan.
# El repacking no entra porque solo reordena lo que ya se recuperó.
LADDER = [
    RetrievalConfig(mode="dense"),
    RetrievalConfig(mode="sparse"),
    RetrievalConfig(mode="hybrid"),
    RetrievalConfig(mode="hybrid", rerank=True),
    RetrievalConfig(mode="hybrid", rewrite=True, rerank=True),
    RetrievalConfig(mode="hybrid", hyde=True, rerank=True),
    RetrievalConfig(mode="hybrid", decompose=True, rerank=True),
    RetrievalConfig(mode="dense", contextual=True),
    RetrievalConfig(mode="hybrid", contextual=True),
    RetrievalConfig(mode="hybrid", contextual=True, rerank=True),
]


class CaseResult(BaseModel):
    config: str
    case_id: str
    case_type: str
    rank: int | None  # posición del primer chunk correcto (None si no apareció)
    recall: float
    ms: int
    top_score: float | None
    retrieved: str


def score_of(chunk: ProcessedChunk) -> float | None:
    if chunk.rerank_score is not None:
        return chunk.rerank_score
    return chunk.score


def missing_evidence(cases: list[GoldenCase], chunks: list[ProcessedChunk]) -> list[str]:
    """Referencias del dataset que no coinciden con ningún chunk (errores del dataset)."""
    missing = []
    for case in cases:
        for group in case.evidence:
            for ref in group:
                if not any(matches(chunk, ref) for chunk in chunks):
                    missing.append(
                        f"{case.id}: {ref.doc_id} {ref.section or ''} {ref.contains or ''}"
                    )
    return missing


def run_case(retriever, cfg: RetrievalConfig, case: GoldenCase) -> CaseResult:
    start = time.perf_counter()
    # Sin filtros: se busca con la pregunta tal como la escribe el usuario
    chunks = retriever.retrieve_context(case.question, {}, K)
    ms = int((time.perf_counter() - start) * 1000)
    return CaseResult(
        config=cfg.label,
        case_id=case.id,
        case_type=case.type,
        rank=first_relevant_rank(chunks, case.evidence, K),
        recall=recall_at_k(chunks, case.evidence, K),
        ms=ms,
        top_score=score_of(chunks[0]) if chunks else None,
        retrieved=" ".join(c.chunk_id for c in chunks),
    )


def summarize(cfg: RetrievalConfig, results: list[CaseResult], cost: dict) -> dict:
    with_evidence = [r for r in results if r.case_type != "negative"]
    n = len(with_evidence)
    hits = [1 for r in with_evidence if r.rank is not None]
    reciprocal = [1 / r.rank for r in with_evidence if r.rank is not None]
    latencies = [r.ms for r in results]
    return {
        "config": cfg.label,
        "cases": n,
        "hit@5": round(len(hits) / n, 3),
        "mrr@5": round(sum(reciprocal) / n, 3),
        "recall@5": round(sum(r.recall for r in with_evidence) / n, 3),
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        **cost,
    }


def suggest_threshold(results: list[CaseResult]) -> dict:
    """Umbral más alto que no deja fuera ninguna pregunta con evidencia encontrada.

    Con él se ve cuántas preguntas sin evidencia (negativas) quedan bloqueadas.
    """
    found = [r.top_score for r in results if r.case_type != "negative" and r.rank == 1]
    negatives = [r.top_score for r in results if r.case_type == "negative"]
    if not found or not negatives:
        return {}
    threshold = min(found)
    blocked = [s for s in negatives if s < threshold]
    return {
        "threshold": round(threshold, 3),
        "negatives_scores": [round(s, 3) for s in negatives],
        "negatives_blocked": f"{len(blocked)} de {len(negatives)}",
    }


def save(summaries: list[dict], results: list[CaseResult], threshold: dict) -> None:
    OUT.mkdir(exist_ok=True)
    data = {"summary": summaries, "threshold": threshold}
    (OUT / "ablation.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))

    with (OUT / "ablation.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    with (OUT / "ablation_cases.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(CaseResult.model_fields))
        writer.writeheader()
        writer.writerows(r.model_dump() for r in results)


def main(container: Container, only: str | None = None, log=print) -> None:
    cases = [c for c in load_golden() if c.evidence or c.type == "negative"]
    configs = [cfg for cfg in LADDER if only is None or cfg.label == only]

    for contextual in (False, True):
        chunks = [ProcessedChunk(**p) for p in container.store(contextual).payloads()]
        for problem in missing_evidence(cases, chunks):
            log(f"Evidencia sin chunk: {problem}")

    summaries, all_results = [], []
    tracker = container.tracker
    for cfg in configs:
        retriever = container.retriever(cfg)
        tokens_in, tokens_out, usd = tracker.tokens_in, tracker.tokens_out, tracker.usd

        results = [run_case(retriever, cfg, case) for case in cases]

        cost = {
            "tokens_in": tracker.tokens_in - tokens_in,
            "tokens_out": tracker.tokens_out - tokens_out,
            "usd": round(tracker.usd - usd, 5),
        }
        summary = summarize(cfg, results, cost)
        summaries.append(summary)
        all_results += results
        log(
            f"{cfg.label:<28} hit@5 {summary['hit@5']:.2f}  mrr {summary['mrr@5']:.2f}  "
            f"recall {summary['recall@5']:.2f}  p50 {summary['p50_ms']} ms  USD {cost['usd']}"
        )

    # El umbral se calibra con la configuración que usa el agente
    agent = container.agent_retrieval().label
    threshold = suggest_threshold([r for r in all_results if r.config == agent])
    save(summaries, all_results, threshold)
    log(f"Umbral para {agent}: {threshold}")
