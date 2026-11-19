import re
from pathlib import Path

from bs4 import BeautifulSoup

from asesoria.domain.models import ProcessedChunk, SourceDoc
from asesoria.domain.ports import Loader


class HtmlSectionLoader(Loader):
    """Páginas web de la SEC: una sección por cada encabezado h2/h3."""

    def load(self, doc: SourceDoc, path: Path) -> list[ProcessedChunk]:
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "lxml")
        root = soup.find("main") or soup.find("article") or soup.body or soup
        for tag in root(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        sections: list[tuple[str, list[str]]] = [("Introducción", [])]
        for el in root.find_all(["h2", "h3", "p", "li"]):
            text = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            if not text:
                continue
            if el.name in ("h2", "h3"):
                sections.append((text, []))
            else:
                sections[-1][1].append(text)

        chunks = []
        for i, (title, paragraphs) in enumerate(sections):
            if title.lower().startswith("more in this section"):
                continue
            if len(" ".join(paragraphs).split()) < 20:
                continue
            chunks.append(
                ProcessedChunk(
                    chunk_id=f"{doc.id}-s{i:02d}",
                    content=f"{title}\n" + "\n".join(paragraphs),
                    doc_id=doc.id,
                    doc_type=doc.doc_type,
                    ticker=doc.ticker,
                    section=title,
                    source_url=doc.url,
                )
            )
        return chunks
