from openai import OpenAI

from asesoria.domain.ports import Embedder


class OpenAIEmbedder(Embedder):
    def __init__(self, client: OpenAI, model: str, tracker=None, batch_size: int = 100):
        self.client = client
        self.model = model
        self.tracker = tracker
        self.batch_size = batch_size

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            resp = self.client.embeddings.create(model=self.model, input=batch)
            if self.tracker:
                self.tracker.add(self.model, resp.usage.total_tokens, 0, 0)
            vectors.extend(item.embedding for item in resp.data)
        return vectors
