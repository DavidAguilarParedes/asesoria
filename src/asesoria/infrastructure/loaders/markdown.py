import re
from pathlib import Path

from asesoria.domain.models import ProcessedChunk, SourceDoc
from asesoria.domain.ports import Loader


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
            body = parts[i + 1].strip()
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
