from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from asesoria.domain.models import ProcessedChunk, SourceDoc
from asesoria.domain.ports import ChunkContextualizer, ChunkingStrategy, Loader


@dataclass
class DownloadReport:
    ok: list[str] = field(default_factory=list)
    manual: list[SourceDoc] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def download_corpus(sources: list[SourceDoc], fetch, raw_dir: Path) -> DownloadReport:
    report = DownloadReport()
    for doc in sources:
        try:
            path = fetch(doc, raw_dir)
        except Exception as exc:  # noqa: BLE001
            report.failed[doc.id] = str(exc)
            continue
        if path is None:
            report.manual.append(doc)
        else:
            report.ok.append(doc.id)
    return report


def load_units(
    docs: list[tuple[SourceDoc, Path]], loader_for: Callable[[SourceDoc], Loader]
) -> list[ProcessedChunk]:
    units: list[ProcessedChunk] = []
    for doc, path in docs:
        units.extend(loader_for(doc).load(doc, path))
    return units


def build_chunks(
    docs: list[tuple[SourceDoc, Path]],
    loader_for: Callable[[SourceDoc], Loader],
    chunker: ChunkingStrategy,
) -> list[ProcessedChunk]:
    return chunker.split(load_units(docs, loader_for))


def add_context(
    chunks: list[ProcessedChunk],
    units: list[ProcessedChunk],
    contextualizer: ChunkContextualizer,
) -> list[ProcessedChunk]:
    """Contextual Retrieval: cada chunk recibe una frase que lo ubica en su sección."""
    by_id = {u.chunk_id: u.content for u in units}
    out = []
    for chunk in chunks:
        section = by_id.get(chunk.parent_id or "", chunk.content)
        context = contextualizer.situate(section, chunk)
        out.append(chunk.model_copy(update={"context": context}))
    return out
