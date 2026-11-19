"""Compacta las respuestas del MCP de Alpaca antes de que lleguen al modelo."""

import json

from mcp import types


def _bars_summary(bars_by_symbol: dict) -> dict:
    summary = {}
    for symbol, bars in bars_by_symbol.items():
        if not bars:
            continue
        closes = [b["c"] for b in bars]
        first, last = bars[0], bars[-1]
        summary[symbol] = {
            "desde": first["t"][:10],
            "hasta": last["t"][:10],
            "barras": len(bars),
            "cierre_inicial": round(first["c"], 2),
            "cierre_final": round(last["c"], 2),
            "cambio_pct": round((last["c"] - first["c"]) / first["c"] * 100, 2),
            "minimo": round(min(b["l"] for b in bars), 2),
            "maximo": round(max(b["h"] for b in bars), 2),
            "cierre_hace_20_barras": round(closes[-21], 2) if len(closes) > 20 else None,
        }
    return summary


def _text(result: types.CallToolResult) -> str:
    return "".join(getattr(c, "text", "") for c in result.content)


def compact_result(result: types.CallToolResult) -> str:
    """Las barras diarias se resumen; el resto pasa igual, incluido el aviso de seguridad."""
    raw = _text(result)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    security = payload.get("_alpaca_mcp_security", {})
    data = payload.get("data")
    if security.get("tool_name") == "get_stock_bars" and isinstance(data, dict):
        payload["data"] = {"resumen_barras": _bars_summary(data.get("bars", {}))}
    return json.dumps(payload, ensure_ascii=False)
