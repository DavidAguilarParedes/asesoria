"""Validación en código de las órdenes, independiente de lo que decida el modelo."""

import json
from dataclasses import dataclass, field

from pydantic import BaseModel


class GateDecision(BaseModel):
    allowed: bool
    reason: str = ""


@dataclass
class OrderGate:
    approved_symbols: set[str]
    # Última validación de idoneidad por símbolo: (aprobada, cantidad validada)
    validations: dict[str, tuple[bool, float]] = field(default_factory=dict)
    # Datos de esa validación, para armar el resumen de la orden
    details: dict[str, dict] = field(default_factory=dict)

    def record_validation(self, arguments: dict, result_json: str) -> None:
        try:
            result = json.loads(result_json)
        except (json.JSONDecodeError, TypeError):
            return
        symbol = str(arguments.get("simbolo", "")).upper()
        if symbol:
            self.validations[symbol] = (bool(result.get("approved")), float(arguments["cantidad"]))
            self.details[symbol] = {
                "precio_usd": arguments.get("precio"),
                "costo_estimado_usd": result.get("costo_estimado_usd"),
                "porcentaje_del_portafolio": result.get("porcentaje_del_portafolio"),
                "idoneidad": result.get("reason"),
            }

    def summary(self, arguments: dict) -> dict:
        symbol = str(arguments.get("symbol", "")).upper()
        return {
            "simbolo": symbol,
            "cantidad": arguments.get("qty"),
            "lado": arguments.get("side"),
            **self.details.get(symbol, {}),
            "cuenta": "paper trading",
        }

    def check(self, arguments: dict) -> GateDecision:
        symbol = str(arguments.get("symbol", "")).upper()
        if arguments.get("side", "").lower() != "buy":
            return GateDecision(allowed=False, reason="solo se permiten órdenes de compra")
        if symbol not in self.approved_symbols:
            return GateDecision(allowed=False, reason=f"{symbol} no está en el universo aprobado")
        if arguments.get("notional") or not arguments.get("qty"):
            return GateDecision(allowed=False, reason="la orden debe indicar una cantidad (qty)")
        advanced = (
            "order_class",
            "advanced_instructions",
            "take_profit_limit_price",
            "stop_loss_stop_price",
            "trail_price",
            "trail_percent",
        )
        if any(arguments.get(name) for name in advanced if arguments.get(name) != "simple"):
            return GateDecision(allowed=False, reason="solo se permiten órdenes simples")

        validation = self.validations.get(symbol)
        if validation is None:
            return GateDecision(allowed=False, reason="la orden no pasó por validar_idoneidad")
        approved, validated_qty = validation
        if not approved:
            return GateDecision(allowed=False, reason="validar_idoneidad rechazó esta orden")
        if float(arguments["qty"]) > validated_qty:
            return GateDecision(
                allowed=False,
                reason=f"la cantidad supera la validada ({validated_qty:g} acciones)",
            )
        return GateDecision(allowed=True)
