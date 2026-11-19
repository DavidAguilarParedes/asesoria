# 0001 · Arquitectura por capas

**Contexto:** el pipeline RAG tiene piezas que queremos intercambiar para compararlas (loaders, chunking, embeddings, vector store, búsqueda, reranking).

**Decisión:** ports & adapters simplificado. Las interfaces viven en `domain/ports.py` y las implementaciones en `infrastructure/`. Todo se arma en `bootstrap.py`. Microsoft Agent Framework y el MCP de Alpaca se usan directamente, sin envolverlos.

**Alternativas:** estructura plana (más simple, pero cambiar piezas obliga a tocar varios archivos); clean architecture completa (repositorios, unit of work, demasiado para este alcance).

**Consecuencias:** la ablación se hace cambiando la composición en `bootstrap.py`. Las reglas de idoneidad se testean sin red. `import-linter` verifica que el dominio no dependa de la infraestructura.
