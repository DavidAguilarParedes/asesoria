import json

from asesoria.infrastructure.judge import Criterion, JudgeVerdict, LiveJudge


class FakeLLM:
    def parse(self, model, system, user, schema, effort="minimal"):
        self.model, self.user, self.effort = model, user, effort
        ok = Criterion(score=1, reason="bien")
        return schema(
            basado_en_fuentes=ok,
            resuelve_lo_pedido=ok,
            uso_de_herramientas=ok,
            respeta_las_reglas=ok,
            veredicto="confiable",
        )


def test_juez_recibe_pregunta_respuesta_y_datos_de_las_tools():
    llm = FakeLLM()
    result = json.dumps({"_alpaca_mcp_security": {"trust": "x"}, "data": {"MSFT": {"p": 498.45}}})
    calls = [{"tool": "get_stock_snapshot", "arguments": {"symbols": "MSFT"}, "result": result}]

    verdict = LiveJudge(llm, "gpt-4.1-mini").judge("¿Precio de MSFT?", "USD 498.45", calls)

    assert isinstance(verdict, JudgeVerdict)
    assert llm.model == "gpt-4.1-mini" and llm.effort is None  # modelo sin razonamiento
    assert "498.45" in llm.user and "¿Precio de MSFT?" in llm.user
    assert "_alpaca_mcp_security" not in llm.user
