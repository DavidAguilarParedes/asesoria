import re

from asesoria.domain.models import ProcessedChunk
from asesoria.domain.ports import ChunkingStrategy


class RecursiveChunker(ChunkingStrategy):
    """Parte las secciones largas en trozos de ~max_words con solape.

    Respeta párrafos y, si un párrafo es muy largo, oraciones.
    """

    def __init__(self, max_words: int = 600, overlap_words: int = 80):
        self.max_words = max_words
        self.overlap_words = overlap_words

    def split(self, chunks: list[ProcessedChunk]) -> list[ProcessedChunk]:
        out: list[ProcessedChunk] = []
        for unit in chunks:
            pieces = self._split_text(unit.content)
            if len(pieces) == 1:
                out.append(unit.model_copy(update={"parent_id": unit.chunk_id}))
                continue
            for i, piece in enumerate(pieces, start=1):
                out.append(
                    unit.model_copy(
                        update={
                            "chunk_id": f"{unit.chunk_id}-{i:02d}",
                            "content": piece,
                            "parent_id": unit.chunk_id,
                        }
                    )
                )
        return out

    def _split_text(self, text: str) -> list[str]:
        if len(text.split()) <= self.max_words:
            return [text]

        blocks: list[str] = []
        for para in text.split("\n"):
            if len(para.split()) <= self.max_words:
                blocks.append(para)
            else:
                blocks.extend(re.split(r"(?<=[.!?])\s+", para))

        pieces: list[str] = []
        current: list[str] = []
        size = 0
        for block in blocks:
            words = len(block.split())
            if current and size + words > self.max_words:
                pieces.append("\n".join(current))
                current, size = self._overlap(current)
            current.append(block)
            size += words
        if current:
            pieces.append("\n".join(current))
        return pieces

    def _overlap(self, blocks: list[str]) -> tuple[list[str], int]:
        kept: list[str] = []
        size = 0
        for block in reversed(blocks):
            words = len(block.split())
            if size + words > self.overlap_words:
                break
            kept.insert(0, block)
            size += words
        return kept, size
