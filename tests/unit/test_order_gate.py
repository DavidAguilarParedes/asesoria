import json

from asesoria.application.order_gate import OrderGate

SYMBOLS = {"AAPL", "MSFT", "NVDA", "SHY", "AGG", "TLT", "IVV"}


def validated_gate(approved: bool = True, qty: float = 5) -> OrderGate:
    gate = OrderGate(approved_symbols=SYMBOLS)
    result = {
        "approved": approved,
        "reason": "OK" if approved else "EXCEDE",
        "costo_estimado_usd": 2542.5,
    }
    gate.record_validation(
        {"simbolo": "msft", "cantidad": qty, "precio": 508.5}, json.dumps(result)
    )
    return gate


def order(**overrides) -> dict:
    return {"symbol": "MSFT", "qty": "5", "side": "buy", "time_in_force": "day", **overrides}


def test_valid_order_passes():
    assert validated_gate().check(order()).allowed


def test_order_without_validation_is_blocked():
    decision = OrderGate(approved_symbols=SYMBOLS).check(order())
    assert not decision.allowed
    assert "validar_idoneidad" in decision.reason


def test_rejected_validation_blocks_order():
    assert not validated_gate(approved=False).check(order()).allowed


def test_more_shares_than_validated_is_blocked():
    assert not validated_gate(qty=5).check(order(qty="6")).allowed


def test_sell_notional_and_advanced_orders_are_blocked():
    gate = validated_gate()
    assert not gate.check(order(side="sell")).allowed
    assert not gate.check(order(qty=None, notional=1000)).allowed
    assert not gate.check(order(order_class="bracket")).allowed
    assert not gate.check(order(symbol="TSLA")).allowed


def test_summary_uses_validation_data():
    summary = validated_gate().summary(order())
    assert summary["simbolo"] == "MSFT"
    assert summary["costo_estimado_usd"] == 2542.5
    assert summary["cuenta"] == "paper trading"
