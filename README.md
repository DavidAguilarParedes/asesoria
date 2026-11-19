# AsesorIA

Agente asesor de inversiones construido con Microsoft Agent Framework. Responde consultas con un RAG sobre documentos financieros públicos, analiza oportunidades combinando ese RAG con datos de mercado del MCP de Alpaca y ejecuta órdenes en paper trading solo después de una confirmación explícita del usuario. Incluye un agente evaluador independiente que calcula cinco métricas de calidad.

> Proyecto de demostración. Nada de lo que responde el agente constituye asesoría financiera real.

## Estado

En construcción. Por ahora contiene el esqueleto del proyecto.

## Requisitos

- [uv](https://docs.astral.sh/uv/)
- Python 3.12 (uv lo instala si no está)
- Una API key de OpenAI
- Una cuenta de paper trading en Alpaca

## Instalación

```bash
uv sync --extra rerank
cp .env.example .env   # y completa las claves
```

## Uso

```bash
uv run asesoria ingest      # descarga e indexa el corpus
uv run asesoria serve       # levanta la API en http://localhost:8000
uv run asesoria eval        # corre el agente evaluador
uv run asesoria ablation    # compara configuraciones del RAG
```

## Variables de entorno

| Variable | Descripción |
|---|---|
| `OPENAI_API_KEY` | API key de OpenAI |
| `OPENAI_CHAT_MODEL` | Modelo de chat (por defecto `gpt-4.1-mini`) |
| `OPENAI_EMBEDDING_MODEL` | Modelo de embeddings (por defecto `text-embedding-3-small`) |
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | Credenciales de la cuenta paper de Alpaca |
| `ALPACA_PAPER_TRADE` | Debe ser `true` |

## Estructura

```
src/asesoria/
├── domain/           modelos, interfaces y reglas de idoneidad (sin dependencias externas)
├── application/      ingesta, recuperación y agente asesor
├── infrastructure/   loaders, embeddings, Qdrant, reranker, MCP de Alpaca, LLM
├── entrypoints/      API (FastAPI) y CLI
├── tools.py          tools del agente
├── config.py         configuración desde .env
└── bootstrap.py      arma las dependencias
src/evaluator/        agente evaluador y ablación
data/                 lista del corpus, políticas internas y clientes de prueba
docs/decisions/       decisiones técnicas
```

Las capas se verifican con `uv run lint-imports`.

## Codespaces

El repo incluye un `.devcontainer`. Para abrirlo en GitHub Codespaces, configura `OPENAI_API_KEY`, `ALPACA_API_KEY` y `ALPACA_SECRET_KEY` como secretos de Codespaces y luego ejecuta `uv run asesoria serve`.

## Corpus

20 documentos: 17 públicos (listados en `data/sources.yaml`) y 3 políticas internas simuladas en `data/policies/`.

## Tiempo invertido

Por completar.
