"""Peças para falar com uma API com limite de uso: classificar o erro, ler o 'tente de novo em X s'
e controlar o ritmo das chamadas (sem chamar demais e sem esperar de menos)."""
import re
import time
from dataclasses import dataclass

_RETRY = re.compile(r"retry(?:Delay|\s+in)?\D{0,15}?(\d+(?:\.\d+)?)\s*s", re.I)
_DIARIA = re.compile(r"PerDay|per day|daily|por dia", re.I)


def espera_sugerida(erro) -> float | None:
    """Lê 'Please retry in 13.2s' ou "'retryDelay': '13s'" na mensagem de erro."""
    m = _RETRY.search(str(erro))
    return float(m.group(1)) if m else None


@dataclass
class Classe:
    tipo: str  # "config" | "cota_diaria" | "limite" | "transitorio"
    espera: float | None = None


def classificar(erro) -> Classe:
    codigo = getattr(erro, "code", None)
    texto = str(erro)
    if codigo in (400, 401, 403, 404):
        return Classe("config")
    if codigo == 429 or "RESOURCE_EXHAUSTED" in texto:
        if _DIARIA.search(texto):
            return Classe("cota_diaria")
        return Classe("limite", espera_sugerida(erro))
    return Classe("transitorio", espera_sugerida(erro))  # 5xx, rede, timeout...


class Limitador:
    """Espaça as chamadas (máx. por minuto) e guarda por quanto tempo cada modelo está 'de castigo'."""

    def __init__(self, max_rpm: float = 10, relogio=time.monotonic):
        self.intervalo = 60.0 / max_rpm if max_rpm and max_rpm > 0 else 0.0
        self.relogio = relogio
        self._proximo = 0.0
        self._bloqueios: dict[str, float] = {}

    def preparar(self, modelo: str, orcamento: float) -> float | None:
        """Quanto esperar antes de chamar. None se passar do orçamento de espera."""
        agora = self.relogio()
        espera = max(self._proximo - agora, self._bloqueios.get(modelo, 0.0) - agora, 0.0)
        return None if espera > orcamento else espera

    def marcar_chamada(self):
        self._proximo = self.relogio() + self.intervalo

    def bloquear(self, modelo: str, segundos: float):
        self._bloqueios[modelo] = self.relogio() + segundos

    def restante(self, modelo: str) -> float:
        return max(0.0, self._bloqueios.get(modelo, 0.0) - self.relogio())
