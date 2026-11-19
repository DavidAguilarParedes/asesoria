import os

from agent_framework import MCPStdioTool

from asesoria.config import Settings
from asesoria.infrastructure.mcp_results import compact_result

SERVER = "alpaca-mcp-server==2.4.1"

# El servidor expone 39 tools. El agente solo ve estas:
ALLOWED_TOOLS = [
    "get_account_info",
    "get_all_positions",
    "get_stock_snapshot",
    "get_stock_bars",
    "get_news",
    "place_stock_order",
    "get_order_by_id",
]

# Lo que mueve dinero exige aprobación humana; lo que solo lee, no.
APPROVAL = {"always_require_approval": ["place_stock_order"], "default": "never_require"}

RISK = {
    "get_account_info": "medio",
    "get_all_positions": "medio",
    "place_stock_order": "alto",
}


class LiveTradingNotAllowed(RuntimeError):
    pass


def alpaca_mcp(settings: Settings) -> MCPStdioTool:
    if not settings.alpaca_paper_trade:
        raise LiveTradingNotAllowed(
            "El piloto solo opera en paper trading (ALPACA_PAPER_TRADE=true)"
        )
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        raise RuntimeError("Faltan ALPACA_API_KEY y ALPACA_SECRET_KEY en .env")

    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "ALPACA_API_KEY": settings.alpaca_api_key.get_secret_value(),
        "ALPACA_SECRET_KEY": settings.alpaca_secret_key.get_secret_value(),
        # Se fija aquí para que nunca dependa de otra configuración
        "ALPACA_PAPER_TRADE": "true",
        "ALPACA_TOOLSETS": "account,trading,stock-data,news",
        "FASTMCP_SHOW_SERVER_BANNER": "false",
        "FASTMCP_LOG_LEVEL": "ERROR",
        "FASTMCP_CHECK_FOR_UPDATES": "off",
    }
    # En Docker, uvx encuentra el servidor ya descargado en la imagen gracias a UV_CACHE_DIR
    for name in ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_TOOL_DIR"):
        if name in os.environ:
            env[name] = os.environ[name]
    return MCPStdioTool(
        name="alpaca",
        command="uvx",
        args=[SERVER],
        env=env,
        load_prompts=False,
        allowed_tools=ALLOWED_TOOLS,
        approval_mode=APPROVAL,
        parse_tool_results=compact_result,
        request_timeout=60,
    )
