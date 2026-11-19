import re
from pathlib import Path

from asesoria.domain.models import ProcessedChunk, SourceDoc
from asesoria.domain.ports import Loader


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def tables_to_sentences(body: str, context: str) -> str:
    """Convierte cada fila de una tabla Markdown en una oración que se entiende sola."""
    lines = body.splitlines()
    out: list[str] = []
    header: list[str] | None = None
    for line in lines:
        if not line.strip().startswith("|"):
            header = None
            out.append(line)
            continue
        cells = _cells(line)
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if header is None:
            header = cells
            continue
        values = ", ".join(f"{col} {val}" for col, val in zip(header[1:], cells[1:], strict=False))
        out.append(f"{context}: {cells[0]}: {values}.")
    return "\n".join(out)


class MarkdownLoader(Loader):
    """Políticas internas: una sección por cada encabezado ## o ###."""

    def load(self, doc: SourceDoc, path: Path) -> list[ProcessedChunk]:
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"^# (.+)$", text, re.M)
        doc_title = title_match.group(1).strip() if title_match else doc.id

        parts = re.split(r"^(#{2,3} .+)$", text, flags=re.M)
        chunks = []
        for i in range(1, len(parts), 2):
            heading = parts[i].lstrip("#").strip()
            body = tables_to_sentences(parts[i + 1].strip(), f"{doc_title}, {heading.lower()}")
            if not body:
                continue
            chunks.append(
                ProcessedChunk(
                    chunk_id=f"{doc.id}-{i // 2 + 1:02d}",
                    content=f"{doc_title} - {heading}\n{body}",
                    doc_id=doc.id,
                    doc_type=doc.doc_type,
                    section=heading,
                    source_url=doc.url,
                )
            )
        return chunks
