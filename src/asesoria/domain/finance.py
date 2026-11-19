"""Cálculos financieros simples. El agente los usa para no hacer aritmética por su cuenta."""


def order_cost(qty: float, price: float) -> float:
    return round(qty * price, 2)


def portfolio_pct(amount: float, portfolio_value: float) -> float:
    return round(amount / portfolio_value * 100, 2)


def max_amount(portfolio_value: float, limit_pct: float) -> float:
    return round(portfolio_value * limit_pct / 100, 2)


def max_shares(amount: float, price: float) -> int:
    return int(amount // price)


def pct_return(initial: float, final: float) -> float:
    return round((final - initial) / initial * 100, 2)


def cagr(initial: float, final: float, years: float) -> float:
    return round(((final / initial) ** (1 / years) - 1) * 100, 2)


def allocation(total: float, weights: dict[str, float]) -> dict[str, float]:
    """Reparte un monto según pesos en porcentaje. Los pesos deben sumar 100."""
    total_weight = sum(weights.values())
    if abs(total_weight - 100) > 0.01:
        raise ValueError(f"los pesos suman {total_weight}, deben sumar 100")
    return {name: round(total * w / 100, 2) for name, w in weights.items()}
