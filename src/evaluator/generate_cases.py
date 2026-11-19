"""Genera casos de evaluación con Ragas a partir de personas.

Sigue el flujo recomendado por Ragas: documentos de LangChain, transformaciones por
defecto, la distribución por defecto (single-hop y multi-hop) adaptada al español y
personas definidas por nosotros. Los casos generados se revisan a mano antes de usarlos.
"""

import asyncio
import json
from collections import defaultdict
from pathlib import Path

from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.testset import TestsetGenerator
from ragas.testset.graph import KnowledgeGraph, Node, NodeType
from ragas.testset.persona import Persona
from ragas.testset.synthesizers import default_query_distribution
from ragas.testset.transforms import apply_transforms, default_transforms

from asesoria.bootstrap import Container
from evaluator.judge import GPT5Wrapper, record_usage
from evaluator.metrics import normalize

OUT = Path("data/eval/ragas_raw.json")

# Se genera por grupo porque Ragas recorre los documentos en orden y se detiene al
# llegar al total pedido: con un solo llamado casi todo saldría del primer documento.
GROUPS = {
    "politicas": (
        6,
        ["politica-limites-de-concentracion", "politica-perfiles-de-riesgo", "politica-idoneidad"],
    ),
    "etfs": (
        8,
        [
            "shy-factsheet",
            "agg-factsheet",
            "tlt-factsheet",
            "ivv-factsheet",
            "tlt-prospectus",
            "agg-prospectus",
        ],
    ),
    "10-k": (6, ["nvda-10k-2026", "aapl-10k-2026", "msft-10k-2026"]),
    "guias": (
        5,
        ["sec-interest-rate-risk", "sec-etfs", "sec-corporate-bonds", "sec-asset-allocation"],
    ),
    # Preguntas que cruzan un instrumento con las reglas internas
    "cruce": (
        6,
        [
            "nvda-10k-2026",
            "politica-limites-de-concentracion",
            "politica-perfiles-de-riesgo",
            "tlt-factsheet",
            "ivv-factsheet",
        ],
    ),
}

# Los nombres van en inglés porque el LLM de Ragas los traduce al emparejar
# personas con temas, y después no los encuentra por nombre.
PERSONAS = [
    Persona(
        name="Junior Advisor",
        role_description="Asesor de inversiones recién contratado en un banco. Necesita "
        "entender las políticas internas y los productos para explicárselos a sus clientes.",
    ),
    Persona(
        name="Conservative Client",
        role_description="Jubilado que quiere proteger su capital. Pregunta en lenguaje "
        "simple por riesgos, bonos y si algo es seguro.",
    ),
    Persona(
        name="Aggressive Client",
        role_description="Profesional joven con horizonte largo, interesado en acciones "
        "tecnológicas y en cuánto puede invertir.",
    ),
    Persona(
        name="Risk Analyst",
        role_description="Analista que revisa límites de concentración, idoneidad y riesgos "
        "de cada instrumento, con términos técnicos.",
    ),
]

SPANISH = (
    "\n\nEscribe siempre la pregunta y la respuesta en español, aunque el contexto esté en "
    "inglés. La respuesta debe tener como máximo tres oraciones."
)


def load_documents(container: Container) -> dict[str, str]:
    parts = defaultdict(list)
    for p in sorted(container.store(False).payloads(), key=lambda p: p["chunk_id"]):
        # De los 10-K solo se usan los primeros chunks de riesgos para no gastar de más
        if "10k" in p["doc_id"] and not (p.get("section") or "").startswith("Item 1A"):
            continue
        parts[p["doc_id"]].append(p["content"])
    texts = {}
    for doc_id, chunks in parts.items():
        if "10k" in doc_id:
            chunks = chunks[:6]
        texts[doc_id] = "\n\n".join(chunks)
    return texts


async def spanish_distribution(llm):
    distribution = default_query_distribution(llm)
    for synthesizer, _ in distribution:
        prompts = await synthesizer.adapt_prompts("spanish", llm=llm)
        prompts["query_answer_generation_prompt"].instruction += SPANISH
        synthesizer.set_prompts(**prompts)
    return distribution


def source_docs(contexts: list[str], texts: dict[str, str]) -> list[str]:
    """De qué documento salió cada contexto (Ragas no guarda los metadatos)."""
    found = []
    for ctx in contexts:
        ctx = ctx.split("\n\n", 1)[-1] if ctx.startswith("<") else ctx  # quita <1-hop>
        start = normalize(ctx)[:150]
        for doc_id, text in texts.items():
            if start in normalize(text):
                found.append(doc_id)
                break
        else:
            found.append("?")
    return found


def build_graph(docs: list[Document], llm, embeddings) -> KnowledgeGraph:
    """Grafo de conocimiento con las transformaciones por defecto de Ragas."""
    kg = KnowledgeGraph()
    for doc in docs:
        properties = {"page_content": doc.page_content, "document_metadata": doc.metadata}
        kg.nodes.append(Node(type=NodeType.DOCUMENT, properties=properties))
    apply_transforms(kg, default_transforms(documents=docs, llm=llm, embedding_model=embeddings))
    return kg


def generate_group(generator: TestsetGenerator, size: int, distribution, log) -> list[dict]:
    """Intenta con todos los tipos de pregunta; si un grupo no tiene relaciones para las
    multi-hop, prueba sin ellas."""
    options = [distribution, distribution[:2], distribution[:1]]
    for option in options:
        weights = [(synthesizer, 1 / len(option)) for synthesizer, _ in option]
        try:
            return generator.generate(testset_size=size, query_distribution=weights).to_list()
        except ValueError as error:
            names = [synthesizer.name for synthesizer, _ in option]
            log(f"  no se pudo con {names}: {error}")
    return []


def main(container: Container, model: str = "gpt-5-mini", log=print) -> None:
    key = container.settings.openai_api_key.get_secret_value()
    llm = GPT5Wrapper(ChatOpenAI(model=model, api_key=key, reasoning_effort="low"))
    embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model=container.settings.openai_embedding_model, api_key=key)
    )
    texts = load_documents(container)

    rows = []
    with get_usage_metadata_callback() as usage:
        # Orden: single-hop, multi-hop abstracta, multi-hop específica
        distribution = asyncio.run(spanish_distribution(llm))
        for group, (size, doc_ids) in GROUPS.items():
            docs = [Document(page_content=texts[d], metadata={"doc_id": d}) for d in doc_ids]
            kg = build_graph(docs, llm, embeddings)
            generator = TestsetGenerator(
                llm=llm, embedding_model=embeddings, knowledge_graph=kg, persona_list=PERSONAS
            )
            samples = generate_group(generator, size, distribution, log)
            for sample in samples:
                rows.append(
                    {
                        "group": group,
                        "synthesizer": sample["synthesizer_name"],
                        "question": sample["user_input"],
                        "reference": sample["reference"],
                        "docs": source_docs(sample["reference_contexts"], texts),
                    }
                )
            log(f"{group}: {len(samples)} casos")

    record_usage(container.tracker, usage.usage_metadata)
    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    for model_name, u in usage.usage_metadata.items():
        log(f"{model_name}: {u['input_tokens']:,} tokens in · {u['output_tokens']:,} out")
    log(f"{len(rows)} casos guardados en {OUT}")
