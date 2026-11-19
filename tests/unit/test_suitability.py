from asesoria.domain.models import ClientProfile, Order, RiskProfile
from asesoria.domain.suitability import Reason, check_order

profile = ClientProfile(
    client_id="c-002",
    name="Cliente Moderado",
    risk_profile=RiskProfile.MODERATE,
    portfolio_value_usd=10_000,
    horizon_years=5,
)


def test_rejects_symbol_outside_universe():
    result = check_order(profile, Order(symbol="TSLA", qty=1, est_price_usd=300))
    assert not result.approved
    assert result.reason == Reason.NOT_APPROVED


def test_accepts_approved_symbol():
    result = check_order(profile, Order(symbol="MSFT", qty=5, est_price_usd=400))
    assert result.approved
