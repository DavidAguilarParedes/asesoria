FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_CACHE_DIR=/opt/uv-cache \
    HF_HOME=/opt/models/huggingface \
    FASTEMBED_CACHE_PATH=/opt/models/fastembed \
    PATH=/opt/venv/bin:$PATH \
    HOME=/tmp \
    PYTHONUNBUFFERED=1 \
    MLFLOW_DISABLE_AGENT_HINT=1

WORKDIR /app

# Primero las dependencias (capa que casi no cambia), después el código.
# Se instala con una caché temporal y se borra, para no dejar 1.8 GB de paquetes en la imagen.
COPY pyproject.toml uv.lock README.md ./
RUN UV_CACHE_DIR=/tmp/uv-build uv sync --frozen --no-dev --no-install-project \
      --extra rerank --extra eval --extra tracking \
 && rm -rf /tmp/uv-build
# Se descargan en la imagen el reranker, el modelo BM25 y el servidor MCP de Alpaca,
# así el contenedor arranca sin esperar descargas. Va antes del código para no repetirlo
# en cada cambio.
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1')" \
 && python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm25', cache_dir='/opt/models/fastembed')" \
 && uvx --from alpaca-mcp-server==2.4.1 python -c "print('alpaca-mcp-server listo')" \
 && chmod -R a+rwX /opt/models /opt/uv-cache

COPY src ./src
RUN UV_CACHE_DIR=/tmp/uv-build uv sync --frozen --no-dev --extra rerank --extra eval --extra tracking \
 && rm -rf /tmp/uv-build

COPY data ./data

EXPOSE 8000
CMD ["sh", "-c", "asesoria init && asesoria serve --port 8000"]
