from datetime import datetime, timedelta

FORMATO = "%Y-%m-%d %H:%M:%S"


class Relogio:
    """Relógio da demo: hora real + um deslocamento que o simulador pode avançar."""

    def __init__(self, banco):
        self.banco = banco

    def _offset(self) -> float:
        row = self.banco.um("SELECT valor FROM kv WHERE chave='relogio_offset_s'")
        return float(row["valor"]) if row else 0.0

    def agora(self) -> datetime:
        return datetime.now().replace(microsecond=0) + timedelta(seconds=self._offset())

    def agora_str(self) -> str:
        return self.agora().strftime(FORMATO)

    def avancar(self, horas: float):
        self.banco.exec("INSERT OR REPLACE INTO kv(chave, valor) VALUES ('relogio_offset_s', ?)",
                        (str(self._offset() + horas * 3600),))

    def em(self, horas: float) -> str:
        return (self.agora() + timedelta(hours=horas)).strftime(FORMATO)
