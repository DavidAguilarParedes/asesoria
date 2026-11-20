"""Function tools del agente.

Siguen las recomendaciones de Anthropic para tools: pocas, con nombres claros, respuestas
cortas con citas y errores que orientan al agente. Cada una lleva su nivel de riesgo
(guía de agentes de OpenAI).
"""

import json
from typing import Annotated, Literal

from agent_framework import tool
from pydantic import Field

from asesoria.domain import finance
from asesoria.domain.models import DocType, Order
from asesoria.domain.ports import ClientRepository, RetrievalStrategy
from asesoria.domain.suitability import SuitabilityRules, check_order

MAX_WORDS_PER_RESULT = 180


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False)


def _cite(chunk) -> str:
    parts = [chunk.doc_id, chunk.section]
    if chunk.page:
        parts.append(f"p. {chunk.page}")
    if chunk.as_of:
        parts.append(f"al {chunk.as_of.isoformat()}")
    return ", ".join(p for p in parts if p)


def _short(text: str) -> str:
    words = text.split()
    return " ".join(words[:MAX_WORDS_PER_RESULT]) + (
        " …" if len(words) > MAX_WORDS_PER_RESULT else ""
    )


def build_tools(
    retriever: RetrievalStrategy,
    clients: ClientRepository,
    rules: SuitabilityRules,
    min_score: float,
    k: int = 5,
):
    approved = sorted(rules.approved_symbols)

    @tool(
        name="buscar_documentos",
        description=(
            "Busca en la base documental: 10-K de AAPL, MSFT y NVDA; fact sheets y prospectos "
            "de SHY, AGG, TLT e IVV; guías de la SEC; y las políticas internas (perfiles, "
            "límites e idoneidad). Úsala para cualquier afirmación sobre riesgos, negocio, "
            "características de un fondo o reglas internas. Devuelve fragmentos con su cita."
        ),
        additional_properties={"riesgo": "bajo"},
    )
    def buscar_documentos(
        consulta: Annotated[str, Field(description="Términos de búsqueda en inglés")],
        ticker: Annotated[
            str | None, Field(description=f"Filtra por instrumento: {', '.join(approved)}")
        ] = None,
        tipo_documento: Annotated[
            Literal["10-K", "fact_sheet", "summary_prospectus", "guide", "policy"] | None,
            Field(description="Filtra por tipo de documento solo si hace falta"),
        ] = None,
    ) -> str:
        if ticker and ticker.upper() not in approved:
            return _json(
                {
                    "error": f"{ticker} no está en el universo aprobado",
                    "hint": f"Instrumentos con documentos: {', '.join(approved)}",
                }
            )
        # Las guías y las políticas no tienen ticker: con ese filtro nunca aparecerían
        if tipo_documento in ("guide", "policy"):
            ticker = None
        filters = {"ticker": ticker.upper() if ticker else None, "doc_type": tipo_documento}
        chunks = retriever.retrieve_context(consulta, filters, k)

        def score(c):
            return c.rerank_score if c.rerank_score is not None else c.score or 0.0

        relevant = [c for c in chunks if score(c) >= min_score]
        if not relevant:
            return _json(
                {
                    "sin_evidencia": True,
                    "hint": "No hay documentos que respalden esto. Prueba otros términos o "
                    "quita filtros; si sigue sin resultados, responde que no tienes "
                    "información suficiente.",
                }
            )
        return _json(
            {
                "resultados": [
                    {
                        "citation_id": c.chunk_id,
                        "cita": _cite(c),
                        "texto": _short(c.content),
                        "score": round(score(c), 3),
                    }
                    for c in relevant
                ]
            }
        )

    @tool(
        name="perfil_cliente",
        description="Devuelve el perfil de riesgo del cliente, su portafolio y sus límites.",
        additional_properties={"riesgo": "bajo"},
    )
    def perfil_cliente(client_id: Annotated[str, Field(description="ID del cliente")]) -> str:
        profile = clients.get(client_id)
        if profile is None:
            return _json({"error": f"cliente {client_id} no existe"})
        limits = rules.concentration[profile.risk_profile]
        by_symbol = {
            symbol: f"{limits[asset_class]:.0%}"
            for symbol, asset_class in rules.instruments.items()
        }
        max_usd = {
            symbol: round(limits[asset_class] * profile.portfolio_value_usd, 2)
            for symbol, asset_class in rules.instruments.items()
        }
        return _json(
            {
                **profile.model_dump(mode="json"),
                "limite_por_instrumento": by_symbol,
                "monto_maximo_usd_por_instrumento": max_usd,
                "max_orden_usd": rules.max_order_usd,
                "no_aptos": [s for s, pct in by_symbol.items() if pct == "0%"],
            }
        )

    @tool(
        name="calculadora_financiera",
        description=(
            "Cálculos exactos. Operaciones: costo_orden(cantidad, precio), "
            "porcentaje_portafolio(monto, valor_portafolio), "
            "monto_maximo(valor_portafolio, porcentaje), acciones_maximas(monto, precio), "
            "retorno(valor_inicial, valor_final), cagr(valor_inicial, valor_final, anios), "
            "asignacion(monto, pesos) con pesos en porcentaje que suman 100."
        ),
        additional_properties={"riesgo": "bajo"},
    )
    def calculadora_financiera(
        operacion: Literal[
            "costo_orden",
            "porcentaje_portafolio",
            "monto_maximo",
            "acciones_maximas",
            "retorno",
            "cagr",
            "asignacion",
        ],
        cantidad: float | None = None,
        precio: float | None = None,
        monto: float | None = None,
        valor_portafolio: float | None = None,
        porcentaje: float | None = None,
        valor_inicial: float | None = None,
        valor_final: float | None = None,
        anios: float | None = None,
        pesos: dict[str, float] | None = None,
    ) -> str:
        try:
            match operacion:
                case "costo_orden":
                    result = finance.order_cost(cantidad, precio)
                case "porcentaje_portafolio":
                    result = finance.portfolio_pct(monto, valor_portafolio)
                case "monto_maximo":
                    result = finance.max_amount(valor_portafolio, porcentaje)
                case "acciones_maximas":
                    result = finance.max_shares(monto, precio)
                case "retorno":
                    result = finance.pct_return(valor_inicial, valor_final)
                case "cagr":
                    result = finance.cagr(valor_inicial, valor_final, anios)
                case "asignacion":
                    result = finance.allocation(monto, pesos or {})
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            return _json({"error": f"faltan datos o son inválidos para {operacion}: {exc}"})
        return _json({"operacion": operacion, "resultado": result})

    @tool(
        name="validar_idoneidad",
        description=(
            "Valida una orden de compra contra el perfil del cliente y las políticas. "
            "Úsala siempre antes de proponer o ejecutar una compra. Si se rechaza, devuelve "
            "el motivo y el monto máximo permitido para proponer una alternativa."
        ),
        additional_properties={"riesgo": "bajo"},
    )
    def validar_idoneidad(
        client_id: str,
        simbolo: str,
        cantidad: float,
        precio: Annotated[float | None, Field(description="Precio actual por acción")] = None,
        posicion_actual_usd: float = 0.0,
        poder_de_compra_usd: float | None = None,
    ) -> str:
        profile = clients.get(client_id)
        if profile is None:
            return _json({"error": f"cliente {client_id} no existe"})
        order = Order(symbol=simbolo, qty=cantidad, est_price_usd=precio)
        result = check_order(profile, order, rules, posicion_actual_usd, poder_de_compra_usd)
        cost = order.est_cost_usd
        pct = finance.portfolio_pct(cost, profile.portfolio_value_usd) if cost else None
        # Cuántas acciones caben en el límite: así el agente no tiene que calcularlo
        max_qty = None
        if precio and result.max_allowed_usd is not None:
            max_qty = int(result.max_allowed_usd // precio)
        return _json(
            {
                **result.model_dump(mode="json"),
                "costo_estimado_usd": cost,
                "porcentaje_del_portafolio": pct,
                "cantidad_maxima_acciones": max_qty,
            }
        )

    return [buscar_documentos, perfil_cliente, calculadora_financiera, validar_idoneidad]


__all__ = ["build_tools", "DocType"]
