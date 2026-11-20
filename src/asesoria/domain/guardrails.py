import re

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


# Frases típicas de un intento de saltarse las reglas (prompt injection). Es la primera
# capa: responde al instante sin llamar al modelo; el prompt del agente es la segunda.
INJECTION_PATTERNS = [
    r"\b(ignora|olvida|omite|sáltate|saltate)\b.{0,40}\b(instrucciones|reglas|indicaciones)",
    r"\bignore\b.{0,40}\b(instructions|rules)\b",
    r"\bsin (pedirme |pedir |solicitar )?(confirmaci[oó]n|aprobaci[oó]n)",
    r"\b(revela|muestra|dime|imprime)\b.{0,30}\b(prompt|instrucciones)",
    r"\b(system prompt|developer mode|modo desarrollador)\b",
]


def is_prompt_injection(text: str) -> bool:
    text = text.lower()
    return any(re.search(p, text) for p in INJECTION_PATTERNS)
