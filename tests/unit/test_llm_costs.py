from types import SimpleNamespace

import pytest

from asesoria.infrastructure.llm import LLM, BudgetExceeded, CostTracker


def test_cost_uses_cached_price_and_stops_at_budget():
    tracker = CostTracker(max_usd=0.01)
    tracker.add("gpt-5-nano", tokens_in=100_000, cached=50_000, tokens_out=10_000)
    # 50k * 0.05 + 50k * 0.005 + 10k * 0.40, por millón
    assert tracker.usd == pytest.approx(0.00675)
    with pytest.raises(BudgetExceeded):
        tracker.add("gpt-5-mini", tokens_in=100_000, cached=0, tokens_out=0)


class FakeCompletions:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        usage = SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=100,
            prompt_tokens_details=SimpleNamespace(cached_tokens=0),
        )
        message = SimpleNamespace(content="respuesta")
        return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=message)])


def test_second_identical_call_is_free(tmp_path):
    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    tracker = CostTracker(max_usd=1.0)
    llm = LLM(client, tracker, tmp_path / "llm.sqlite")

    assert llm.text("gpt-5-nano", "sys", "hola") == "respuesta"
    cost_after_first = tracker.usd
    assert llm.text("gpt-5-nano", "sys", "hola") == "respuesta"

    assert completions.calls == 1
    assert tracker.usd == cost_after_first
