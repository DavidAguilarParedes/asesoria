import re

from asesoria.domain.models import ProcessedChunk
from evaluator.dataset import EvidenceRef


def normalize(text: str) -> str:
    # Los PDF traen dobles espacios y saltos de línea en medio de las frases
    return re.sub(r"\s+", " ", text).strip().lower()


def matches(chunk: ProcessedChunk, ref: EvidenceRef) -> bool:
    """¿El chunk está en el lugar que indica la referencia?"""
    if chunk.doc_id != ref.doc_id:
        return False
    if ref.section and not normalize(chunk.section or "").startswith(normalize(ref.section)):
        return False
    if ref.page is not None and chunk.page != ref.page:
        return False
    if ref.contains and normalize(ref.contains) not in normalize(chunk.content):
        return False
    return True


def is_relevant(chunk: ProcessedChunk, groups: list[list[EvidenceRef]]) -> bool:
    return any(matches(chunk, ref) for group in groups for ref in group)


def first_relevant_rank(chunks: list[ProcessedChunk], groups, k: int) -> int | None:
    """Posición (1, 2, 3...) del primer chunk correcto entre los k primeros."""
    for position, chunk in enumerate(chunks[:k], start=1):
        if is_relevant(chunk, groups):
            return position
    return None


def recall_at_k(chunks: list[ProcessedChunk], groups, k: int) -> float:
    """Fracción de grupos encontrados. Importa en preguntas que comparan dos instrumentos."""
    if not groups:
        return 0.0
    top = chunks[:k]
    found = 0
    for group in groups:
        if any(is_relevant(chunk, [group]) for chunk in top):
            found += 1
    return found / len(groups)


def percentile(values: list[int], p: int) -> int:
    ordered = sorted(values)
    index = round(p / 100 * (len(ordered) - 1))
    return ordered[index]
