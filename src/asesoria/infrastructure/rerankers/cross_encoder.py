from asesoria.domain.ports import Reranker

# Multilingüe: las preguntas llegan en español y los documentos están en inglés
DEFAULT_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"


class CrossEncoderReranker(Reranker):
    """Corre local en CPU, sin costo por consulta."""

    def __init__(self, model_name: str = DEFAULT_MODEL, max_length: int = 512):
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name, max_length=max_length)

    def score(self, query: str, texts: list[str]) -> list[float]:
        return [float(s) for s in self.model.predict([(query, t) for t in texts])]
