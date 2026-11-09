from collections import defaultdict


class Hub:
    """Guarda os WebSockets abertos (um por celular do app fake) e entrega as mensagens."""

    def __init__(self):
        self._conexoes = defaultdict(set)

    async def conectar(self, telefone, ws):
        await ws.accept()
        self._conexoes[telefone].add(ws)

    def desconectar(self, telefone, ws):
        self._conexoes[telefone].discard(ws)

    async def _mandar(self, telefone, evento):
        for ws in list(self._conexoes.get(telefone, ())):
            try:
                await ws.send_json(evento)
            except Exception:
                self._conexoes[telefone].discard(ws)

    async def enviar(self, saidas):
        for s in saidas:
            await self._mandar(s.para, s.para_evento())

    async def digitando(self, telefone, ativo=True):
        await self._mandar(telefone, {"tipo": "digitando", "ativo": ativo})
