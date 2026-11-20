import json

from mcp import types

from asesoria.infrastructure.mcp_results import compact_result


def result(payload: dict) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(payload))])


def test_bars_are_summarized_and_security_note_is_kept():
    bars = [
        {"t": f"2026-10-{d:02d}T04:00:00Z", "o": 100, "h": 100 + d, "l": 90, "c": 100 + d}
        for d in range(1, 31)
    ]
    payload = {
        "_alpaca_mcp_security": {"tool_name": "get_stock_bars", "trust": "untrusted_tool_output"},
        "data": {"bars": {"MSFT": bars}},
    }
    out = json.loads(compact_result(result(payload)))
    summary = out["data"]["resumen_barras"]["MSFT"]
    assert summary["cierre_inicial"] == 101
    assert summary["cierre_final"] == 130
    assert summary["cambio_pct"] == 28.71
    assert summary["barras"] == 30
    assert summary["cierres_semanales"] == [105, 110, 115, 120, 125, 130]
    assert out["_alpaca_mcp_security"]["trust"] == "untrusted_tool_output"


def test_other_tools_pass_through():
    payload = {"_alpaca_mcp_security": {"tool_name": "get_news"}, "data": {"news": [1, 2]}}
    assert json.loads(compact_result(result(payload)))["data"] == {"news": [1, 2]}
