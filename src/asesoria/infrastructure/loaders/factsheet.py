import re
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

from asesoria.domain.models import ProcessedChunk, SourceDoc
from asesoria.domain.ports import Loader

SECTIONS = [
    "FUND DESCRIPTION",
    "CALENDAR YEAR PERFORMANCE",
    "ANNUALIZED PERFORMANCE",
    "KEY FACTS",
    "FEES AND EXPENSES BREAKDOWN",
    "FUND CHARACTERISTICS",
    "TOP HOLDINGS",
    "TOP SECTORS",
    "MATURITY BREAKDOWN",
    "CREDIT RATINGS",
]
# Secciones que no aportan datos del fondo
STOP = ("GLOSSARY", "IMPORTANT INFORMATION", "Contact Us", "RATINGS", "GROWTH OF HYPOTHETICAL")


def _as_of(text: str):
    m = re.search(r"as of (\w+ \d{1,2}, \d{4})", text)
    return datetime.strptime(m.group(1), "%B %d, %Y").date() if m else None


def _fund_name(text: str, ticker: str) -> str:
    m = re.search(r"(iShares[^\n]+ETF)", text)
    return m.group(1).strip() if m else ticker


VALUE_AT_END = re.compile(r"^(?P<key>.*[A-Za-z)].*?)\s+(?P<value>-?\$?[\d,]+(\.\d+)?%?( yrs)?)$")
ONLY_VALUE = re.compile(r"^-?\$?[\d,]+(\.\d+)?%?$")


def _merge_rows(lines: list[str]) -> list[tuple[str, str | None]]:
    # Junta filas que el PDF partió en varias líneas. Devuelve (clave, valor) o (texto, None).
    rows: list[tuple[str, str | None]] = []
    buffer: list[str] = []
    for line in lines:
        if " : " in line:
            if buffer and rows:
                key, value = rows[-1]
                extra = " ".join(buffer)
                rows[-1] = (key, f"{value} {extra}") if value else (f"{key} {extra}", None)
                buffer = []
            key, value = line.split(" : ", 1)
            rows.append((key.strip(), value.strip()))
        elif ONLY_VALUE.match(line) and buffer:
            rows.append((" ".join(buffer), line))
            buffer = []
        elif m := VALUE_AT_END.match(line):
            key = " ".join([*buffer, m.group("key")])
            rows.append((key, m.group("value")))
            buffer = []
        else:
            buffer.append(line)
    if buffer:
        rows.append((" ".join(buffer), None))
    return rows


NUMBER = re.compile(r"^-?[\d.]+$")
TABLE_SECTIONS = {"CALENDAR YEAR PERFORMANCE", "ANNUALIZED PERFORMANCE"}


def _table_to_sentences(lines: list[str], prefix: str) -> list[str]:
    # Tablas de rentabilidad: primera línea = columnas, luego filas "NAV 1.2 3.4 ..."
    cols: list[str] = []
    out: list[str] = []
    for line in lines:
        toks = line.split()
        nums = [t for t in toks if NUMBER.match(t)]
        if not cols:
            cols = toks
        elif not out and not nums and len(toks) <= 2:
            cols += toks
        elif len(nums) >= 3:
            label = " ".join(t for t in toks if not NUMBER.match(t))
            cols = " ".join(cols).replace("Since Inception", "Since-Inception").split()
            cells = zip(cols, nums, strict=False)
            pairs = ", ".join(f"{c.replace('-', ' ')} {v}%" for c, v in cells)
            out.append(f"{prefix} {label}: {pairs}.")
        else:
            out.append(line)
    return out


def _rows_to_sentences(lines: list[str], prefix: str, percent: bool) -> list[str]:
    out = []
    for key, value in _merge_rows(lines):
        if value and percent and not value.endswith("%"):
            value += "%"
        out.append(f"{prefix} {key}: {value}." if value else key)
    return out


class FactSheetLoader(Loader):
    def load(self, doc: SourceDoc, path: Path) -> list[ProcessedChunk]:
        text = "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
        as_of = _as_of(text)
        fund = _fund_name(text, doc.ticker or "")
        prefix = f"{doc.ticker} ({fund}) -"

        sections: dict[str, list[str]] = {}
        percent: set[str] = set()
        current = None
        for raw in text.splitlines():
            line = re.sub(r"\s+", " ", raw).strip()
            if not line:
                continue
            header = next((s for s in SECTIONS if line.upper().startswith(s)), None)
            if header:
                current = header
                sections.setdefault(current, [])
                if "(%)" in line:
                    percent.add(header)
                continue
            if line.startswith(STOP):
                current = None
                continue
            if current and line != "Fund":
                sections[current].append(line)

        chunks = []
        for name, lines in sections.items():
            if not lines:
                continue
            if name in TABLE_SECTIONS:
                body = "\n".join(_table_to_sentences(lines, prefix))
            else:
                body = "\n".join(_rows_to_sentences(lines, prefix, name in percent))
            title = name.title()
            date_txt = f" (al {as_of.isoformat()})" if as_of else ""
            chunks.append(
                ProcessedChunk(
                    chunk_id=f"{doc.id}-{name.lower().replace(' ', '-')}",
                    content=f"{fund} - {title}{date_txt}\n{body}",
                    doc_id=doc.id,
                    doc_type=doc.doc_type,
                    ticker=doc.ticker,
                    section=title,
                    as_of=as_of,
                    source_url=doc.url,
                )
            )
        return chunks
