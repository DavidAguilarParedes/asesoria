"""Agente que interpreta los resultados de la evaluación y escribe el análisis de fallos.

No calcula métricas: solo lee las que ya calculó el pipeline.
"""

import json
from typing import Annotated

from agent_framework import Agent, tool
from pydantic import Field

INSTRUCTIONS = """Eres un analista de calidad de un asistente de inversiones con RAG.
Recibes las métricas de una evaluación y la lista de casos que fallaron en alguna métrica.

Qué mide cada métrica (de 0 a 1):
- faithfulness: si lo que dice la respuesta está respaldado por lo que trajeron las tools.
- correctness: si la respuesta coincide con la respuesta de referencia.
- goal_accuracy: si el agente logró lo que el usuario quería en la conversación.
- tool_call_accuracy: si usó las tools esperadas, en orden y con los argumentos clave.
- guardrails: si cumplió las reglas (disclaimer, no ejecutar sin confirmación, decir que no
  sabe, rechazar temas ajenos o inyecciones).
- hit@5 y mrr@5: si las búsquedas del agente trajeron el documento correcto (RAG).

Escribe en español un informe breve en Markdown con estas secciones:
1. Resumen: 3 o 4 líneas con los números clave.
2. Patrones de fallo: agrupa los casos por causa probable (recuperación, respuesta no
   respaldada por las fuentes, comportamiento del agente o error del propio dataset) y
   cita sus ids. Explica cada patrón con un ejemplo concreto.
3. Recomendaciones: cambios concretos, ordenados por impacto.

Usa la herramienta ver_caso para leer la pregunta, la respuesta y las tools de los casos
que necesites antes de sacar conclusiones. No inventes números: usa solo los datos
entregados. Si una métrica tiene pocos casos, dilo."""


def build_agent(chat_client, details: dict[str, dict]) -> Agent:
    @tool(name="ver_caso", description="Devuelve el detalle de un caso de la evaluación.")
    def ver_caso(case_id: Annotated[str, Field(description="Id del caso, por ejemplo tk-03")]):
        return json.dumps(details.get(case_id, {"error": "no existe"}), ensure_ascii=False)

    return Agent(chat_client, INSTRUCTIONS, name="interprete", tools=[ver_caso])


async def interpret(
    chat_client, summary: dict, failures: list[dict], details: dict, on_usage
) -> str:
    agent = build_agent(chat_client, details)
    message = (
        f"Métricas:\n{json.dumps(summary, indent=1, ensure_ascii=False)}\n\n"
        f"Casos con fallos:\n{json.dumps(failures, indent=1, ensure_ascii=False)}"
    )
    response = await agent.run(message)
    on_usage(dict(response.usage_details or {}))
    return response.text
