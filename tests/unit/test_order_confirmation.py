import json

from asesoria.application.advisor import order_confirmation


def alpaca(**order):
    return json.dumps({"_alpaca_mcp_security": {}, "data": order})


def test_orden_aceptada_con_el_mercado_cerrado():
    text = order_confirmation(alpaca(symbol="MSFT", qty="2", status="accepted"))
    assert text.startswith("✅ Orden enviada: compra de 2 MSFT")
    assert "aceptada" in text and "próxima apertura" in text


def test_orden_ejecutada_muestra_el_precio():
    text = order_confirmation(
        alpaca(symbol="AAPL", qty="2", status="filled", filled_avg_price="350.4")
    )
    assert text == "✅ Orden ejecutada: compra de 2 AAPL a USD 350.40 por acción (paper trading)."


def test_orden_bloqueada_por_las_reglas():
    blocked = json.dumps({"bloqueada": True, "motivo": "no fue validada"})
    assert order_confirmation(blocked) == "No se envió la orden: no fue validada."


def test_respuesta_desconocida_deja_el_texto_del_modelo():
    assert order_confirmation("error de red") is None
    assert order_confirmation(json.dumps({"data": {"foo": 1}})) is None
