import json
from pathlib import Path

from asesoria.domain.models import ClientProfile
from asesoria.domain.ports import ClientRepository


class JsonClientRepository(ClientRepository):
    """Clientes simulados guardados en data/clientes.json."""

    def __init__(self, path: Path):
        rows = json.loads(path.read_text(encoding="utf-8"))
        self._clients = {row["client_id"]: ClientProfile(**row) for row in rows}

    def get(self, client_id: str) -> ClientProfile | None:
        return self._clients.get(client_id)

    def all(self) -> list[ClientProfile]:
        return list(self._clients.values())
