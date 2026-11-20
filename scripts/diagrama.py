# Dibuja docs/arquitectura.svg (coordenadas a mano). Para el PNG se abre el SVG en un navegador.
W, H = 1800, 890
out = []


def box(x, y, w, h, title, sub="", kind="box"):
    fill, stroke = {
        "box": ("#e6eeee", "#5a8084"),
        "hot": ("#fdeeeb", "#ea6852"),
        "store": ("#3a5a5d", "#2c4547"),
        "user": ("#2c4547", "#2c4547"),
    }[kind]
    color, subc = ("#fff", "#d5e2e3") if kind in ("store", "user") else ("#2b2d30", "#5d6266")
    r = h / 2 if kind == "user" else 12
    out.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>'
    )
    cy = y + h / 2 - (9 if sub else 0)
    out.append(
        f'<text x="{x + w / 2}" y="{cy + 5}" text-anchor="middle" font-size="17" font-weight="700" fill="{color}">{title}</text>'
    )
    if sub:
        out.append(
            f'<text x="{x + w / 2}" y="{cy + 27}" text-anchor="middle" font-size="13.5" fill="{subc}">{sub}</text>'
        )


def group(x, y, w, h, title, bottom=False):
    out.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="#f7f9f9" stroke="#bcd0d1" stroke-width="1.5"/>'
    )
    ty = y + h - 16 if bottom else y + 30
    out.append(
        f'<text x="{x + 18}" y="{ty}" font-size="14" font-weight="700" fill="#5a8084" letter-spacing="1.2">{title.upper()}</text>'
    )


def arrow(d, label="", lx=0, ly=0, dashed=False, hot=False):
    color = "#ea6852" if hot else "#5a8084"
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    out.append(
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"{dash} marker-end="url(#{"ah" if hot else "a"})"/>'
    )
    if label:
        tw = len(label) * 7.4 + 14
        out.append(
            f'<rect x="{lx - tw / 2}" y="{ly - 13}" width="{tw}" height="22" rx="6" fill="#fff"/>'
        )
        out.append(
            f'<text x="{lx}" y="{ly + 3}" text-anchor="middle" font-size="13" fill="{color}" font-weight="600">{label}</text>'
        )


out.append(
    f'<text x="40" y="52" font-size="28" font-weight="800" fill="#2c4547">Asesor<tspan fill="#ea6852">IA</tspan> · Arquitectura</text>'
)
out.append(
    '<text x="40" y="80" font-size="15" fill="#5d6266">Agente asesor con RAG, MCP de Alpaca y aprobación humana · agente evaluador independiente</text>'
)

# Entrada
box(40, 330, 120, 56, "Asesor", kind="user")
box(195, 300, 200, 116, "Página web", "chat · documentos · evaluación")
box(430, 300, 200, 116, "API FastAPI", "/chat/stream · /chat/approve")
arrow("M160 358 H190")
arrow("M395 358 H425")

# Agente asesor
group(665, 110, 540, 480, "Agente asesor · Microsoft Agent Framework")
box(690, 165, 220, 80, "Guardrails en código", "prompt injection · tema", "hot")
box(690, 300, 220, 116, "Agente gpt-5-mini", "decide qué tools usar")
box(690, 470, 220, 90, "Prompt base", "rol · límites · disclaimer")
box(955, 165, 225, 80, "OrderGate", "valida la orden en código")
box(955, 300, 225, 116, "Memoria de sesión", "AgentSession + perfil")
box(955, 470, 225, 90, "Aprobación humana", "tarjeta Aprobar / Rechazar", "hot")
arrow("M630 358 H660 V205 H685")
arrow("M800 245 V295")
arrow("M800 470 V421")
arrow("M910 358 H950", dashed=True)

# Tools y MCP
group(1245, 110, 330, 300, "Tools locales")
box(1265, 160, 290, 62, "buscar_documentos", "RAG con citas")
box(1265, 236, 290, 62, "perfil_cliente · validar_idoneidad")
box(1265, 312, 290, 62, "calculadora_financiera")
box(1245, 460, 330, 100, "MCP de Alpaca (oficial)", "7 de 39 tools · paper trading", "box")
box(1615, 160, 150, 62, "Qdrant", "híbrido + reranker", "store")
box(1615, 470, 150, 80, "Alpaca", "mercado · órdenes", "store")
arrow("M1205 300 H1240")
arrow("M1205 505 H1240")
arrow("M1555 191 H1610")
arrow("M1575 510 H1610")
arrow("M1245 540 C1220 600 1190 600 1170 565", "place_stock_order", 1250, 598, hot=True)
arrow("M1180 205 H1220 V500 H1240", dashed=True)

# Franja inferior
group(40, 650, 900, 200, "Agente evaluador · independiente")
box(65, 720, 170, 90, "54 casos", "a mano + Ragas")
box(275, 720, 190, 90, "Corre al asesor", "órdenes rechazadas")
box(505, 720, 200, 90, "Juez LLM", "otra familia · Ragas")
box(745, 720, 170, 90, "JSON · CSV", "+ MLflow · análisis")
arrow("M235 765 H270")
arrow("M465 765 H500")
arrow("M705 765 H740")
arrow("M370 720 V680 H760 V595", "pone a prueba al asesor", 560, 680, dashed=True)

group(985, 650, 780, 200, "Observabilidad y calidad en vivo", bottom=True)
box(1010, 690, 230, 90, "MLflow", "una traza por turno", "store")
box(1270, 690, 230, 90, "logs/*.jsonl", "tools y modelo", "store")
box(1530, 690, 210, 90, "Juez en vivo", "gpt-4.1-mini · /judge", "hot")
arrow("M910 400 H932 V625 H1125 V685", "trazas", 1030, 625, dashed=True)
arrow("M1125 625 H1385 V685", dashed=True)

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Segoe UI, Inter, sans-serif">
<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#5a8084"/></marker>
<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#ea6852"/></marker></defs>
<rect width="{W}" height="{H}" fill="#ffffff"/>{"".join(out)}</svg>'''
open("docs/arquitectura.svg", "w", encoding="utf-8").write(svg)
