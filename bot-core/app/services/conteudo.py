import json
from pathlib import Path

from app.config import BASE_DIR


class Conteudo:
    """Pílulas, enquetes e mensagens de acompanhamento (arquivos em content/)."""

    def __init__(self, pilulas, enquetes, mensagens):
        self.pilulas = sorted(pilulas, key=lambda p: (p["semana"], p["id"]))
        self.enquetes = enquetes
        self.mensagens = mensagens

    @classmethod
    def carregar(cls, pasta=None) -> "Conteudo":
        pasta = Path(pasta) if pasta else BASE_DIR / "content"

        def ler(nome):
            return json.loads((pasta / nome).read_text(encoding="utf-8"))
        return cls(ler("pilulas.json"), ler("enquetes.json"), ler("mensagens.json"))

    def pilula(self, id_):
        return next((p for p in self.pilulas if p["id"] == id_), None)

    def enquete(self, id_):
        return next((e for e in self.enquetes if e["id"] == id_), None)

    def proxima_pilula(self, semana_atual, enviadas):
        return next((p for p in self.pilulas if p["semana"] <= semana_atual and p["id"] not in enviadas), None)

    def proxima_enquete(self, enviadas):
        return next((e for e in self.enquetes if e["id"] not in enviadas), None)

    def acompanhamento(self, dia, nome):
        pool = self.mensagens["primeira_semana"] if dia <= 10 else self.mensagens["geral"]
        return pool[dia % len(pool)].format(nome=nome)

    def marco(self, dia, nome):
        modelo = self.mensagens["marcos"].get(str(dia))
        return modelo.format(nome=nome) if modelo else None
