"""Conta as chamadas feitas por modelo no dia (a cota diária do Google zera à meia-noite do horário do Pacífico).
Fica em arquivo, então o servidor e o cli.py somam no mesmo contador."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _dia_da_cota(agora_utc: datetime) -> str:
    try:
        from zoneinfo import ZoneInfo
        return agora_utc.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
    except Exception:  # Windows sem o pacote tzdata
        return (agora_utc - timedelta(hours=8)).date().isoformat()


class UsoDiario:
    def __init__(self, caminho=None, agora=lambda: datetime.now(timezone.utc)):
        self.caminho = Path(caminho) if caminho else None
        self.agora = agora
        self._dados = {}
        self._carregar()

    def _carregar(self):
        dados = {}
        if self.caminho and self.caminho.exists():
            try:
                dados = json.loads(self.caminho.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                dados = {}
        hoje = _dia_da_cota(self.agora())
        self._dados = dados if dados.get("data") == hoje else {"data": hoje, "contagem": {}}

    def total(self, modelo: str) -> int:
        self._carregar()
        return self._dados["contagem"].get(modelo, 0)

    def todos(self) -> dict:
        self._carregar()
        return dict(self._dados["contagem"])

    def registrar(self, modelo: str):
        self._carregar()  # relê: o servidor e o cli.py podem estar rodando ao mesmo tempo
        self._dados["contagem"][modelo] = self._dados["contagem"].get(modelo, 0) + 1
        if self.caminho:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            self.caminho.write_text(json.dumps(self._dados), encoding="utf-8")
