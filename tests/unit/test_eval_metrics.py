from asesoria.domain.models import DocType, ProcessedChunk
from evaluator.ablation import CaseResult, suggest_threshold
from evaluator.dataset import EvidenceRef, load_golden
from evaluator.metrics import first_relevant_rank, matches, percentile, recall_at_k


def chunk(doc_id, section="Item 1A · Risk Factors", content="texto", page=None):
    return ProcessedChunk(
        chunk_id=f"{doc_id}-{section}",
        content=content,
        doc_id=doc_id,
        doc_type=DocType.TEN_K,
        section=section,
        page=page,
    )


def test_matches_por_seccion_pagina_y_frase():
    c = chunk("nvda-10k-2026", content="sales to one  direct\ncustomer represented 22%")
    assert matches(c, EvidenceRef(doc_id="nvda-10k-2026", section="Item 1A"))
    assert matches(c, EvidenceRef(doc_id="nvda-10k-2026", contains="One direct customer"))
    assert not matches(c, EvidenceRef(doc_id="aapl-10k-2026"))
    assert not matches(c, EvidenceRef(doc_id="nvda-10k-2026", section="Item 7"))
    assert not matches(c, EvidenceRef(doc_id="nvda-10k-2026", page=3))


def test_rank_y_recall():
    shy = [EvidenceRef(doc_id="shy-factsheet")]
    tlt = [EvidenceRef(doc_id="tlt-factsheet")]
    chunks = [chunk("agg-factsheet"), chunk("tlt-factsheet"), chunk("ivv-factsheet")]

    assert first_relevant_rank(chunks, [shy, tlt], k=5) == 2
    assert first_relevant_rank(chunks, [shy], k=5) is None
    assert first_relevant_rank(chunks, [tlt], k=1) is None
    # Compara SHY con TLT: solo se encontró uno de los dos
    assert recall_at_k(chunks, [shy, tlt], k=5) == 0.5


def test_percentil():
    assert percentile([10, 20, 30, 40, 50], 50) == 30
    assert percentile([10, 20, 30, 40, 50], 95) == 50


def test_umbral_sugerido():
    def result(case_type, rank, score):
        return CaseResult(
            config="x",
            case_id="c",
            case_type=case_type,
            rank=rank,
            recall=0,
            ms=1,
            top_score=score,
            retrieved="",
        )

    results = [
        result("rag", 1, 3.0),
        result("rag", 1, -1.0),
        result("negative", None, -4.0),
        result("negative", None, 0.5),
    ]
    t = suggest_threshold(results)
    assert t["threshold"] == -1.0
    assert t["negatives_blocked"] == "1 de 2"


def test_golden_bien_formado():
    cases = load_golden()
    assert len(cases) >= 50
    assert any(c.source == "ragas" and c.hops == "multi" for c in cases)
    for case in cases:
        if case.type == "rag":
            assert case.evidence, case.id
        if case.type == "negative":
            assert not case.evidence and case.expect.abstain, case.id
