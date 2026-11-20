import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# USD por millón de tokens: (input, input en caché, output). Fuente: página de precios de OpenAI.
PRICES = {
    "gpt-5-mini": (0.25, 0.025, 2.00),
    "gpt-5-nano": (0.05, 0.005, 0.40),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
    "gpt-4o-mini": (0.15, 0.075, 0.60),
    "text-embedding-3-small": (0.02, 0.02, 0.0),
}


class BudgetExceeded(RuntimeError):
    pass


class CostTracker:
    def __init__(self, max_usd: float):
        self.max_usd = max_usd
        self.usd = 0.0
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0

    def add(self, model: str, tokens_in: int, cached: int, tokens_out: int) -> None:
        price_in, price_cached, price_out = PRICES.get(model, PRICES["gpt-5-mini"])
        self.usd += (
            (tokens_in - cached) * price_in + cached * price_cached + tokens_out * price_out
        ) / 1_000_000
        self.calls += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        if self.usd > self.max_usd:
            raise BudgetExceeded(f"Se superó el tope de USD {self.max_usd:.2f} en esta corrida")

    def summary(self) -> str:
        return (
            f"{self.calls} llamadas · {self.tokens_in:,} tokens in · "
            f"{self.tokens_out:,} tokens out · USD {self.usd:.4f}"
        )

    def save(self, path: Path, command: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "command": command,
            "calls": self.calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "usd": round(self.usd, 6),
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")


class LLM:
    """Cliente de chat con caché en disco y control de gasto."""

    def __init__(self, client: OpenAI, tracker: CostTracker, cache_path: Path):
        self.client = client
        self.tracker = tracker
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(cache_path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS llm (key TEXT PRIMARY KEY, value TEXT)")

    def _cached(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM llm WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _store(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO llm VALUES (?, ?)", (key, value))
        self.db.commit()

    def _track(self, model: str, usage) -> None:
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0
        self.tracker.add(model, usage.prompt_tokens, cached, usage.completion_tokens)

    @staticmethod
    def _key(*parts: str) -> str:
        return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()

    def text(self, model: str, system: str, user: str) -> str:
        key = self._key("text", model, system, user)
        if (hit := self._cached(key)) is not None:
            return hit
        resp = self.client.chat.completions.create(
            model=model,
            reasoning_effort="minimal",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        self._track(model, resp.usage)
        answer = resp.choices[0].message.content or ""
        self._store(key, answer)
        return answer

    def parse(
        self, model: str, system: str, user: str, schema: type[T], effort: str | None = "minimal"
    ) -> T:
        """effort=None para modelos sin razonamiento (por ejemplo gpt-4.1-mini)."""
        key = self._key("parse", model, str(effort or "t0"), schema.__name__, system, user)
        if (hit := self._cached(key)) is not None:
            return schema.model_validate_json(hit)
        # Los modelos sin razonamiento van con temperatura 0: misma entrada, misma salida
        options = {"reasoning_effort": effort} if effort else {"temperature": 0}
        resp = self.client.chat.completions.parse(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=schema,
            **options,
        )
        self._track(model, resp.usage)
        parsed = resp.choices[0].message.parsed
        self._store(key, parsed.model_dump_json())
        return parsed
