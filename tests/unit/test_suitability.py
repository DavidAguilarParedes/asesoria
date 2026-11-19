from pathlib import Path

import pytest

from asesoria.domain.models import ClientProfile, Order, RiskProfile
from asesoria.domain.suitability import Reason, check_order
from asesoria.infrastructure.policies import read_rules

RULES = read_rules(Path("data/policies"))


def client(risk: RiskProfile, value: float = 10_000) -> ClientProfile:
    return ClientProfile(
        client_id="c", name="Cliente", risk_profile=risk, portfolio_value_usd=value, horizon_years=5
    )


def test_rejects_symbol_outside_universe():
    result = check_order(
        client(RiskProfile.MODERATE), Order(symbol="TSLA", qty=1, est_price_usd=300), RULES
    )
    assert result.reason == Reason.NOT_APPROVED


def test_conservative_cannot_buy_single_stock():
    result = check_order(
        client(RiskProfile.CONSERVATIVE), Order(symbol="MSFT", qty=1, est_price_usd=400), RULES
    )
    assert result.reason == Reason.NOT_SUITABLE


def test_moderate_nvda_limit_is_ten_percent():
    # Ejemplo de la política: moderado con USD 10,000 puede poner hasta USD 1,000 en NVDA
    profile = client(RiskProfile.MODERATE)
    too_much = check_order(profile, Order(symbol="NVDA", qty=10, est_price_usd=150), RULES)
    assert too_much.reason == Reason.EXCEEDS_CONCENTRATION
    assert too_much.max_allowed_usd == 1000

    ok = check_order(profile, Order(symbol="NVDA", qty=5, est_price_usd=150), RULES)
    assert ok.approved


def test_moderate_tlt_3000_exceeds_twenty_percent():
    result = check_order(
        client(RiskProfile.MODERATE), Order(symbol="TLT", qty=30, est_price_usd=100), RULES
    )
    assert result.reason == Reason.EXCEEDS_CONCENTRATION
    assert result.max_allowed_usd == 2000


def test_existing_position_counts_toward_limit():
    result = check_order(
        client(RiskProfile.MODERATE),
        Order(symbol="NVDA", qty=4, est_price_usd=150),
        RULES,
        current_position_usd=500,
    )
    assert result.reason == Reason.EXCEEDS_CONCENTRATION
    assert result.max_allowed_usd == 500


def test_order_limit_applies_even_if_concentration_allows():
    result = check_order(
        client(RiskProfile.AGGRESSIVE, value=100_000),
        Order(symbol="IVV", qty=20, est_price_usd=600),
        RULES,
    )
    assert result.reason == Reason.EXCEEDS_ORDER_LIMIT


def test_buying_power():
    result = check_order(
        client(RiskProfile.MODERATE),
        Order(symbol="AGG", qty=10, est_price_usd=100),
        RULES,
        buying_power_usd=500,
    )
    assert result.reason == Reason.NO_BUYING_POWER


@pytest.mark.parametrize("symbol", ["AAPL", "SHY", "IVV"])
def test_missing_price_is_rejected(symbol):
    result = check_order(client(RiskProfile.MODERATE), Order(symbol=symbol, qty=1), RULES)
    assert result.reason == Reason.MISSING_PRICE


def test_menciones_de_instrumentos():
    from asesoria.domain.guardrails import mentioned_tickers

    assert mentioned_tickers("¿Qué relación tiene Microsoft con OpenAI?") == ["MSFT"]
    assert mentioned_tickers("Compara SHY con TLT") == ["SHY", "TLT"]
    assert mentioned_tickers("Dame una receta de ceviche") == []
