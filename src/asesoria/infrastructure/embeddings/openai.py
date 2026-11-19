from openai import OpenAI

from asesoria.domain.ports import Embedder


class OpenAIEmbedder(Embedder):
    def __init__(self, client: OpenAI, model: str, batch_size: int = 100):
        self.client = client
        self.model = model
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            resp = self.client.embeddings.create(model=self.model, input=batch)
            vectors.extend(item.embedding for item in resp.data)
        return vectors
