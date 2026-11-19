from pathlib import Path

import yaml

from asesoria.domain.models import DocType, SourceDoc
from asesoria.domain.suitability import SuitabilityRules


def read_rules(policies_dir: Path) -> SuitabilityRules:
    data = yaml.safe_load((policies_dir / "reglas.yaml").read_text(encoding="utf-8"))
    return SuitabilityRules(**data)


def policy_docs(policies_dir: Path) -> list[SourceDoc]:
    return [
        SourceDoc(id=path.stem, doc_type=DocType.POLICY, url=str(path))
        for path in sorted(policies_dir.glob("*.md"))
    ]
