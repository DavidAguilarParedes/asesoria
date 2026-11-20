# Guion del video de demostración

## Grabación automática

`scripts/grabar_video.py` recorre este guion solo, con subtítulos en pantalla, y graba el video con Playwright y el Edge instalado. Con la app corriendo y **la bolsa abierta**, desde PowerShell en Windows:

```powershell
uv run --no-project --with playwright python \\wsl.localhost\Ubuntu\home\david\dev\asesoria\scripts\grabar_video.py --out $HOME\Videos\asesoria
```

El video queda en `Videos\asesoria` en formato `.webm`, que YouTube y Google Drive aceptan. Llama al agente real: cuesta unos USD 0.04 de API.

## Grabación manual

Duración sugerida: 4 a 5 minutos. Graba la pantalla completa con el navegador a 1440 px o más de ancho.

## Antes de grabar

1. **Horario de mercado:** lunes a viernes de 9:30 a 16:00 (hora de Nueva York, la misma de Lima en noviembre). Fuera de ese horario la orden queda "aceptada" y no se ejecuta en el momento.
2. Levanta todo: `docker compose up -d` y espera a que http://localhost:8000 responda.
3. Abre tres pestañas:
   - http://localhost:8000 (recarga con **Ctrl + F5**)
   - El portal de Alpaca en paper trading, en *Orders*
   - http://localhost:5000 (MLflow)
4. Cancela en el portal de Alpaca las órdenes de prueba que sigan pendientes, para que no confundan.

## Escenario 1 · RAG con citas (≈ 1 min)

1. Cliente **c-002 · Cliente Moderado**.
2. Clic en el ejemplo **"¿Qué riesgos menciona Apple en su último reporte anual?"**.
3. Muestra los pasos en vivo ("Buscando en los documentos ✓").
4. En la respuesta, señala las **citas numeradas** y la lista de **Fuentes**.
5. Clic en una cita: se abre la pestaña Documentos con el fragmento exacto del 10-K resaltado.

## Escenario 2 · Análisis de oportunidades (≈ 1.5 min)

1. Vuelve a Chat, cliente **c-002**, **Nueva conversación**.
2. Clic en **"¿Qué oportunidades ves entre MSFT, NVDA y un ETF de bonos?"**.
3. Comenta los pasos: perfil del cliente, precios, tendencia y noticias en Alpaca (MCP), documentos.
4. Muestra las **tarjetas**: precio y gráfico de 90 días, idoneidad contra el perfil y noticias.
5. Clic en **⚖ Evaluar con el juez**: el panel de la derecha muestra el dictamen de otro modelo con el motivo de cada nota.
6. Opcional: **Ver conversación en MLflow** para mostrar la traza completa (cada llamada al modelo y a las tools).

## Escenario 3 · Orden en paper trading con aprobación (≈ 1.5 min)

1. Cliente **c-003 · Cliente Agresivo**, **Nueva conversación**.
2. Clic en **"Compra 5 acciones de MSFT"**.
3. Aparece la **tarjeta de la orden** (precio, costo, % del portafolio, idoneidad). Di que nada se envía sin aprobación.
4. Clic en **Aprobar orden**.
5. La respuesta confirma con lo que devolvió Alpaca: **"✅ Orden ejecutada: compra de 5 MSFT a USD …"**.
6. Cambia a la pestaña de Alpaca, recarga *Orders*: la orden figura como **filled**. Muestra también *Positions*.

## Cierre (≈ 30 s)

1. Ejemplo de **Seguridad**, el intento de manipulación: se bloquea al instante, sin llamar al modelo.
2. Pestaña **Evaluación**: el agente evaluador, las 5 métricas del juez y los 54 casos.

## Después de grabar

Sube el video (YouTube como no listado, Loom o Google Drive) y pega el link en la sección *Evidencia de ejecución* del README.
