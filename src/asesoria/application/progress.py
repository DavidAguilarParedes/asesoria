"""Avisos de progreso: qué tool está usando el agente en este momento.

La API abre una cola antes de llamar al asesor y la va enviando a la página.
Sin cola (CLI, evaluación) los avisos no hacen nada.
"""

import asyncio
from contextvars import ContextVar

_queue: ContextVar[asyncio.Queue | None] = ContextVar("progress", default=None)


def listen() -> asyncio.Queue:
    """Abre una cola para los avisos de la tarea actual y de las que cree después."""
    queue = asyncio.Queue()
    _queue.set(queue)
    return queue


def notify(event: dict) -> None:
    queue = _queue.get()
    if queue is not None:
        queue.put_nowait(event)


async def events(task: asyncio.Task, queue: asyncio.Queue):
    """Entrega los avisos de la cola mientras la tarea sigue corriendo."""
    while not task.done() or not queue.empty():
        try:
            event = await asyncio.wait_for(queue.get(), timeout=0.2)
        except TimeoutError:
            continue
        yield event
