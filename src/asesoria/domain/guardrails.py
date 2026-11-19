from pydantic import BaseModel

# Alias en español que el código reconoce sin depender del LLM
TICKER_ALIASES = {
    "AAPL": ["apple", "aapl"],
    "MSFT": ["microsoft", "msft"],
    "NVDA": ["nvidia", "nvda"],
    "SHY": ["shy", "bonos de corto plazo", "bonos cortos", "tesoro de 1 a 3"],
    "AGG": ["agg", "bonos agregados", "mercado de bonos agregado"],
    "TLT": ["tlt", "bonos largos", "bonos de largo plazo", "tesoro a 20", "20+ años"],
    "IVV": ["ivv", "s&p 500", "s&p500"],
}


class RelevanceVerdict(BaseModel):
    on_topic: bool
    reason: str


def mentioned_tickers(text: str) -> list[str]:
    text = text.lower()
    return [t for t, aliases in TICKER_ALIASES.items() if any(a in text for a in aliases)]
