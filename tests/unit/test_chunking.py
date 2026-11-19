from asesoria.domain.models import DocType, ProcessedChunk
from asesoria.infrastructure.chunking.recursive import RecursiveChunker


def make_unit(text: str) -> ProcessedChunk:
    return ProcessedChunk(chunk_id="doc-item1a", content=text, doc_id="doc", doc_type=DocType.TEN_K)


def test_short_unit_is_not_split():
    chunks = RecursiveChunker(max_words=50).split([make_unit("una sola linea corta")])
    assert [c.chunk_id for c in chunks] == ["doc-item1a"]


def test_long_unit_is_split_with_stable_ids_and_overlap():
    paragraphs = [f"Parrafo {i} " + "palabra " * 20 for i in range(10)]
    chunks = RecursiveChunker(max_words=60, overlap_words=25).split(
        [make_unit("\n".join(paragraphs))]
    )

    assert len(chunks) > 1
    assert chunks[0].chunk_id == "doc-item1a-01"
    assert all(len(c.content.split()) <= 60 for c in chunks)
    # El último párrafo de un trozo se repite al inicio del siguiente
    assert chunks[0].content.split("\n")[-1] == chunks[1].content.split("\n")[0]
    assert all(c.doc_type == DocType.TEN_K for c in chunks)
