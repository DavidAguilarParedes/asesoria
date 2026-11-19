import hashlib
import json
import sqlite3
from pathlib import Path

from asesoria.domain.ports import Embedder


class CachingEmbedder(Embedder):
    """Proxy: guarda los embeddings en disco para no pagar dos veces el mismo texto."""

    def __init__(self, inner: Embedder, cache_path: Path, namespace: str):
        self.inner = inner
        self.namespace = namespace
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        # MAF ejecuta las tools en otro hilo
        self.db = sqlite3.connect(cache_path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS emb (key TEXT PRIMARY KEY, vec TEXT)")
        self.hits = 0
        self.misses = 0

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.namespace}|{text}".encode()).hexdigest()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        keys = [self._key(t) for t in texts]
        found: dict[str, list[float]] = {}
        for i in range(0, len(keys), 500):
            part = keys[i : i + 500]
            marks = ",".join("?" * len(part))
            rows = self.db.execute(f"SELECT key, vec FROM emb WHERE key IN ({marks})", part)
            found.update((k, json.loads(v)) for k, v in rows)

        missing = [(k, t) for k, t in zip(keys, texts, strict=True) if k not in found]
        self.hits += len(texts) - len(missing)
        self.misses += len(missing)
        if missing:
            vectors = self.inner.embed_texts([t for _, t in missing])
            rows = [(k, json.dumps(v)) for (k, _), v in zip(missing, vectors, strict=True)]
            self.db.executemany("INSERT OR REPLACE INTO emb VALUES (?, ?)", rows)
            self.db.commit()
            found.update((k, v) for (k, _), v in zip(missing, vectors, strict=True))
        return [found[k] for k in keys]
