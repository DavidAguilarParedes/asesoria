import re
from pathlib import Path

from pypdf import PdfReader

from asesoria.domain.models import ProcessedChunk, SourceDoc
from asesoria.domain.ports import Loader

PROSPECTUS_HEADINGS = [
    "Investment Objective",
    "Fees and Expenses",
    "Principal Investment Strategies",
    "Summary of Principal Risks",
    "Performance Information",
    "Management",
    "Purchase and Sale of Fund Shares",
    "Tax Information",
    "Payments to Broker-Dealers and Other Financial Intermediaries",
]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _read_pages(path: Path) -> list[str]:
    return [re.sub(r"[ \t]+", " ", p.extract_text() or "") for p in PdfReader(path).pages]


class PdfSectionLoader(Loader):
    """Corta por encabezados conocidos. Sin encabezados, usa una unidad por página."""

    def __init__(self, headings: list[str] | None = None):
        self.headings = headings or []

    def load(self, doc: SourceDoc, path: Path) -> list[ProcessedChunk]:
        pages = _read_pages(path)
        if self.headings:
            return self._by_headings(doc, pages)
        return self._by_pages(doc, pages)

    def _by_headings(self, doc: SourceDoc, pages: list[str]) -> list[ProcessedChunk]:
        sections: list[tuple[str, int, list[str]]] = []
        current: tuple[str, int, list[str]] | None = None
        for page_no, page in enumerate(pages, start=1):
            for line in page.splitlines():
                clean = line.strip()
                if clean in self.headings:
                    current = (clean, page_no, [])
                    sections.append(current)
                elif current and clean:
                    current[2].append(clean)
        return [
            self._chunk(doc, f"{doc.id}-{_slug(title)}", title, page, "\n".join(lines))
            for title, page, lines in sections
            if lines
        ]

    def _by_pages(self, doc: SourceDoc, pages: list[str]) -> list[ProcessedChunk]:
        return [
            self._chunk(doc, f"{doc.id}-p{n:02d}", f"Página {n}", n, text.strip())
            for n, text in enumerate(pages, start=1)
            if len(text.split()) > 30
        ]

    def _chunk(self, doc, chunk_id, section, page, content) -> ProcessedChunk:
        return ProcessedChunk(
            chunk_id=chunk_id,
            content=content,
            doc_id=doc.id,
            doc_type=doc.doc_type,
            ticker=doc.ticker,
            section=section,
            page=page,
            source_url=doc.url,
        )
