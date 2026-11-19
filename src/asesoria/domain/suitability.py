from enum import StrEnum

from pydantic import BaseModel

from asesoria.domain.models import ClientProfile, Order

APPROVED_SYMBOLS = {"AAPL", "MSFT", "NVDA", "SHY", "AGG", "TLT", "IVV"}


class Reason(StrEnum):
    OK = "OK"
    NOT_APPROVED = "INSTRUMENTO_NO_APROBADO"
    MISSING_PRICE = "SIN_PRECIO"


class SuitabilityResult(BaseModel):
    approved: bool
    reason: Reason
    detail: str = ""


def check_order(profile: ClientProfile, order: Order) -> SuitabilityResult:
    # TODO: límites por perfil desde la política de concentración
    if order.symbol.upper() not in APPROVED_SYMBOLS:
        return SuitabilityResult(approved=False, reason=Reason.NOT_APPROVED, detail=order.symbol)
    if order.est_cost_usd is None:
        return SuitabilityResult(approved=False, reason=Reason.MISSING_PRICE)
    return SuitabilityResult(approved=True, reason=Reason.OK)
