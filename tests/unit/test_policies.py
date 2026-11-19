import re
from pathlib import Path

from asesoria.domain.models import RiskProfile
from asesoria.infrastructure.loaders.markdown import MarkdownLoader
from asesoria.infrastructure.policies import policy_docs, read_rules

POLICIES = Path("data/policies")
CLASS_NAMES = {
    "Acción individual": "accion",
    "Bonos de corto plazo": "bonos_corto",
    "Bonos de mediano plazo": "bonos_medio",
    "Bonos de largo plazo": "bonos_largo",
    "Renta variable amplia": "renta_variable_amplia",
}
PROFILES = [RiskProfile.CONSERVATIVE, RiskProfile.MODERATE, RiskProfile.AGGRESSIVE]


def test_markdown_table_matches_rules_yaml():
    rules = read_rules(POLICIES)
    text = (POLICIES / "politica-limites-de-concentracion.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| ([^|]+?) \| (\d+)% \| (\d+)% \| (\d+)% \|$", text, re.M)
    assert len(rows) == len(CLASS_NAMES)
    for name, *percents in rows:
        asset_class = CLASS_NAMES[name]
        for profile, pct in zip(PROFILES, percents, strict=True):
            assert rules.concentration[profile][asset_class] == int(pct) / 100


def test_markdown_mentions_max_order_and_universe():
    rules = read_rules(POLICIES)
    limits = (POLICIES / "politica-limites-de-concentracion.md").read_text(encoding="utf-8")
    assert f"USD {rules.max_order_usd:,.0f}" in limits
    suitability = (POLICIES / "politica-idoneidad.md").read_text(encoding="utf-8")
    for symbol in rules.approved_symbols:
        assert f"- {symbol} (" in suitability


def test_policies_are_loaded_by_section():
    docs = policy_docs(POLICIES)
    assert len(docs) == 3
    for doc in docs:
        chunks = MarkdownLoader().load(doc, Path(doc.url))
        assert len(chunks) >= 3
        assert all(c.section for c in chunks)
