from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

GOLDEN = Path("data/eval/golden.yaml")


class EvidenceRef(BaseModel):
    doc_id: str
    section: str | None = None
    page: int | None = None
    contains: str | None = None


class Expectation(BaseModel):
    tools: list[str] = []
    abstain: bool = False
    approval: bool | None = None
    blocked: bool = False
    injection: bool = False
    executes: bool | None = None


class GoldenCase(BaseModel):
    id: str
    type: Literal["rag", "negative", "behavior"]
    question: str
    client_id: str | None = None
    # Grupos de lugares válidos: el caso se cubre si aparece al menos uno por grupo
    evidence: list[list[EvidenceRef]] = []
    reference: str
    expect: Expectation = Expectation()


def load_golden(path: Path = GOLDEN) -> list[GoldenCase]:
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = [GoldenCase(**row) for row in rows]
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Hay ids repetidos en el set de evaluación")
    return cases
