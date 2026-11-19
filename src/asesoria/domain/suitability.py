from enum import StrEnum

from pydantic import BaseModel

from asesoria.domain.models import ClientProfile, Order, RiskProfile


class SuitabilityRules(BaseModel):
    instruments: dict[str, str]
    concentration: dict[RiskProfile, dict[str, float]]
    max_order_usd: float

    @property
    def approved_symbols(self) -> set[str]:
        return set(self.instruments)


class Reason(StrEnum):
    OK = "OK"
    NOT_APPROVED = "INSTRUMENTO_NO_APROBADO"
    NOT_SUITABLE = "NO_APTO_PARA_EL_PERFIL"
    EXCEEDS_CONCENTRATION = "EXCEDE_LIMITE_DE_CONCENTRACION"
    EXCEEDS_ORDER_LIMIT = "EXCEDE_MONTO_MAXIMO_POR_ORDEN"
    NO_BUYING_POWER = "PODER_DE_COMPRA_INSUFICIENTE"
    MISSING_PRICE = "SIN_PRECIO"


class SuitabilityResult(BaseModel):
    approved: bool
    reason: Reason
    detail: str = ""
    max_allowed_usd: float | None = None


def _reject(reason: Reason, detail: str, max_allowed: float | None = None) -> SuitabilityResult:
    return SuitabilityResult(
        approved=False, reason=reason, detail=detail, max_allowed_usd=max_allowed
    )


def check_order(
    profile: ClientProfile,
    order: Order,
    rules: SuitabilityRules,
    current_position_usd: float = 0.0,
    buying_power_usd: float | None = None,
) -> SuitabilityResult:
    symbol = order.symbol.upper()
    if symbol not in rules.approved_symbols:
        return _reject(Reason.NOT_APPROVED, f"{symbol} no está en el universo aprobado")

    cost = order.est_cost_usd
    if cost is None:
        return _reject(Reason.MISSING_PRICE, "falta el precio para estimar el costo")

    asset_class = rules.instruments[symbol]
    limit = rules.concentration[profile.risk_profile][asset_class]
    if limit == 0:
        return _reject(
            Reason.NOT_SUITABLE, f"{asset_class} no es apto para perfil {profile.risk_profile}"
        )

    max_position = limit * profile.portfolio_value_usd
    room = max(max_position - current_position_usd, 0.0)
    max_allowed = round(min(room, rules.max_order_usd), 2)

    if current_position_usd + cost > max_position:
        detail = f"límite {limit:.0%} del portafolio para {asset_class}"
        return _reject(Reason.EXCEEDS_CONCENTRATION, detail, max_allowed)
    if cost > rules.max_order_usd:
        detail = f"máximo USD {rules.max_order_usd:,.0f} por orden"
        return _reject(Reason.EXCEEDS_ORDER_LIMIT, detail, max_allowed)
    if buying_power_usd is not None and cost > buying_power_usd:
        return _reject(Reason.NO_BUYING_POWER, f"poder de compra USD {buying_power_usd:,.2f}")

    return SuitabilityResult(approved=True, reason=Reason.OK, max_allowed_usd=max_allowed)
