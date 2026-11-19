from pathlib import Path

import httpx
import yaml

from asesoria.domain.models import SourceDoc


def read_sources(path: Path) -> list[SourceDoc]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [SourceDoc(**item) for item in data]


def download(doc: SourceDoc, raw_dir: Path, user_agent: str, force: bool = False) -> Path | None:
    target = raw_dir / f"{doc.id}{doc.extension}"
    if target.exists() and not force:
        return target
    if doc.manual:
        return None

    headers = {"User-Agent": user_agent} if "sec.gov" in doc.url else {}
    resp = httpx.get(doc.url, headers=headers, follow_redirects=True, timeout=60)
    resp.raise_for_status()
    raw_dir.mkdir(parents=True, exist_ok=True)
    target.write_bytes(resp.content)
    return target
