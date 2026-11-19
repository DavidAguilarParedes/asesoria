import re
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from asesoria.domain.models import ProcessedChunk, SourceDoc
from asesoria.domain.ports import Loader

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Items que usamos y el Item donde termina cada uno
ITEMS = {
    "1": ("Business", "1A"),
    "1A": ("Risk Factors", "1B"),
    "7": ("Management's Discussion and Analysis", "7A"),
    "7A": ("Quantitative and Qualitative Disclosures About Market Risk", "8"),
}
TITLES = {
    "1": "business",
    "1A": "risk factors",
    "1B": "unresolved staff comments",
    "7": "management",
    "7A": "quantitative and qualitative",
    "8": "financial statements",
}
PAGE_NOISE = re.compile(
    r"^(item \d+[a-c]?(, ?\d+[a-c]?)*|part i+|table of contents|\d{1,3}"
    r"|.*\| \d{4} form 10-k \| \d+)$",
    re.I,
)


def _heading_pattern(item: str) -> re.Pattern:
    # Tolera espacios en medio de las palabras (versalitas partidas)
    title = r"\s*".join(re.escape(c) for c in TITLES[item].replace(" ", ""))
    # Solo al inicio de línea, para no confundir citas dentro del texto
    return re.compile(rf"^item\s*{item}\s*[.:]?\s*{title}", re.I | re.M)


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all(lambda t: t.name and t.name.startswith("ix:header")):
        tag.decompose()
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c and c not in {"$", "%", ")"}]
            if cells:
                rows.append(" | ".join(cells))
        table.replace_with("\n" + "\n".join(rows) + "\n")
    text = soup.get_text("\n").replace("\xa0", " ")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln and not PAGE_NOISE.match(ln))


def _find_section(text: str, item: str) -> str:
    end_item = ITEMS[item][1]
    starts = [m.start() for m in _heading_pattern(item).finditer(text)]
    ends = [m.start() for m in _heading_pattern(end_item).finditer(text)]
    best = ""
    for s in starts:
        nxt = next((e for e in ends if e > s), None)
        if nxt is not None and nxt - s > len(best):
            best = text[s:nxt]
    return best.strip()


class EdgarHtmlLoader(Loader):
    def load(self, doc: SourceDoc, path: Path) -> list[ProcessedChunk]:
        text = _html_to_text(path.read_text(encoding="utf-8", errors="ignore"))
        chunks = []
        for item, (title, _) in ITEMS.items():
            body = _find_section(text, item)
            if not body:
                continue
            chunks.append(
                ProcessedChunk(
                    chunk_id=f"{doc.id}-item{item.lower()}",
                    content=body,
                    doc_id=doc.id,
                    doc_type=doc.doc_type,
                    ticker=doc.ticker,
                    section=f"Item {item} · {title}",
                    source_url=doc.url,
                )
            )
        return chunks
