"""Genera el diagrama de arquitectura como archivo de Excalidraw (docs/arquitectura.excalidraw).

    python scripts/diagrama.py

El archivo se puede abrir y editar en https://excalidraw.com. La imagen docs/arquitectura.png
se exporta desde ese archivo con el motor de Excalidraw (ver docs/arquitectura-export.html).
"""

import json
import random
from pathlib import Path

OUT = Path("docs/arquitectura.excalidraw")
random.seed(7)

INK, MUTED = "#1e1e1e", "#5d6266"
COLORS = {  # relleno de cada tipo de caja
    "box": "#e6eeee",
    "hot": "#ffe3dd",
    "store": "#c3d9db",
    "user": "#f3d9a4",
}
elements = []


def base(kind: str, x: float, y: float, w: float, h: float, **extra) -> dict:
    element = {
        "id": f"e{len(elements)}",
        "type": kind,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "angle": 0,
        "strokeColor": INK,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": random.randint(1, 10**9),
        "version": 1,
        "versionNonce": random.randint(1, 10**9),
        "isDeleted": False,
        "boundElements": None,
        "updated": 1,
        "link": None,
        "locked": False,
    }
    element.update(extra)
    elements.append(element)
    return element


def text(
    x: float, y: float, value: str, size: int = 20, color: str = INK, align: str = "center"
) -> None:
    lines = value.split("\n")
    w = max(len(line) for line in lines) * size * 0.56
    h = len(lines) * size * 1.25
    left = x - w / 2 if align == "center" else x
    base(
        "text",
        left,
        y,
        w,
        h,
        text=value,
        originalText=value,
        fontSize=size,
        fontFamily=1,
        textAlign=align,
        verticalAlign="top",
        containerId=None,
        lineHeight=1.25,
        baseline=int(size * 0.9),
        strokeColor=color,
        autoResize=True,
    )


def box(x, y, w, h, title, sub="", kind="box") -> None:
    shape = "ellipse" if kind == "user" else "rectangle"
    base(shape, x, y, w, h, backgroundColor=COLORS[kind], roundness={"type": 3})
    top = y + h / 2 - (22 if sub else 13)
    text(x + w / 2, top, title, 20)
    if sub:
        text(x + w / 2, top + 28, sub, 15, MUTED)


def group(x, y, w, h, title, bottom=False) -> None:
    base(
        "rectangle",
        x,
        y,
        w,
        h,
        backgroundColor="#f7f9f9",
        strokeStyle="dashed",
        strokeColor="#8fb0b3",
        roundness={"type": 3},
        strokeWidth=1,
    )
    text(x + 18, y + h - 34 if bottom else y + 12, title, 17, "#3a5a5d", align="left")


def arrow(points, label="", at=None, dashed=False, hot=False) -> None:
    x0, y0 = points[0]
    rel = [[px - x0, py - y0] for px, py in points]
    xs, ys = [p[0] for p in rel], [p[1] for p in rel]
    base(
        "arrow",
        x0,
        y0,
        max(xs) - min(xs),
        max(ys) - min(ys),
        points=rel,
        strokeColor="#e8590c" if hot else "#3a5a5d",
        strokeStyle="dashed" if dashed else "solid",
        startArrowhead=None,
        endArrowhead="arrow",
        startBinding=None,
        endBinding=None,
        lastCommittedPoint=None,
        roundness={"type": 2},
    )
    if label:
        text(at[0], at[1], label, 15, "#e8590c" if hot else "#3a5a5d")


text(40, 26, "AsesorIA · Arquitectura", 36, "#2c4547", align="left")
text(
    40,
    76,
    "Agente asesor con RAG, MCP de Alpaca y aprobación humana · agente evaluador independiente",
    17,
    MUTED,
    align="left",
)

# Entrada
box(30, 322, 140, 72, "Asesor", kind="user")
box(195, 300, 210, 116, "Página web", "chat · evaluación")
box(435, 300, 205, 116, "API FastAPI", "/chat · /approve")
arrow([[170, 358], [190, 358]])
arrow([[405, 358], [430, 358]])

# Agente asesor
group(665, 110, 545, 480, "Agente asesor · Microsoft Agent Framework")
box(690, 165, 225, 85, "Guardrails en código", "prompt injection · tema", "hot")
box(690, 300, 225, 116, "Agente gpt-5-mini", "decide qué tools usar")
box(690, 470, 225, 95, "Prompt base", "rol · límites · aviso")
box(960, 165, 225, 85, "OrderGate", "valida la orden en código")
box(960, 300, 225, 116, "Memoria de sesión", "AgentSession + perfil")
box(960, 470, 225, 95, "Aprobación humana", "Aprobar / Rechazar", "hot")
arrow([[640, 358], [655, 358], [655, 207], [685, 207]])
arrow([[802, 250], [802, 295]])
arrow([[802, 470], [802, 421]])
arrow([[915, 358], [955, 358]], dashed=True)

# Tools y MCP
group(1245, 110, 330, 300, "Tools locales")
box(1265, 160, 290, 64, "buscar_documentos", "RAG con citas")
box(1265, 236, 290, 64, "perfil_cliente", "validar_idoneidad")
box(1265, 312, 290, 64, "calculadora_financiera")
box(1245, 460, 330, 104, "MCP de Alpaca", "7 de 39 tools · paper trading")
box(1615, 160, 160, 66, "Qdrant", "híbrido + reranker", "store")
box(1615, 470, 160, 84, "Alpaca", "mercado · órdenes", "store")
arrow([[1210, 300], [1240, 300]])
arrow([[1210, 510], [1240, 510]])
arrow([[1555, 192], [1610, 192]])
arrow([[1575, 512], [1610, 512]])
arrow([[1245, 548], [1215, 600], [1190, 568]], "place_stock_order", (1262, 600), hot=True)
arrow([[1185, 207], [1225, 207], [1225, 495], [1240, 495]], dashed=True)

# Franja inferior
group(30, 650, 910, 210, "Agente evaluador · independiente")
box(55, 710, 175, 100, "54 casos", "a mano + Ragas")
box(265, 710, 200, 100, "Corre al asesor", "órdenes rechazadas")
box(500, 710, 200, 100, "Juez LLM", "otra familia · Ragas")
box(735, 710, 180, 100, "JSON · CSV", "MLflow · análisis")
arrow([[230, 760], [260, 760]])
arrow([[465, 760], [495, 760]])
arrow([[700, 760], [730, 760]])
arrow(
    [[365, 710], [365, 680], [760, 680], [760, 595]],
    "pone a prueba al asesor",
    (560, 652),
    dashed=True,
)

group(985, 650, 790, 210, "Observabilidad y calidad en vivo", bottom=True)
box(1010, 680, 230, 100, "MLflow", "una traza por turno", "store")
box(1270, 680, 230, 100, "logs/*.jsonl", "tools y modelo", "store")
box(1530, 680, 220, 100, "Juez en vivo", "gpt-4.1-mini · /judge", "hot")
arrow(
    [[915, 400], [935, 400], [935, 625], [1125, 625], [1125, 675]],
    "trazas",
    (1030, 600),
    dashed=True,
)
arrow([[1125, 625], [1385, 625], [1385, 675]], dashed=True)

OUT.write_text(
    json.dumps(
        {
            "type": "excalidraw",
            "version": 2,
            "source": "https://excalidraw.com",
            "elements": elements,
            "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
            "files": {},
        },
        ensure_ascii=False,
        indent=1,
    ),
    encoding="utf-8",
)
print(f"{OUT} · {len(elements)} elementos")
