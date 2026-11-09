"""Cadência dos 90 dias: decide, para cada colaborador, se hoje o bot puxa conversa e com que tipo de mensagem."""
from app.services import jornada
from app.services.conversa import Saida


class Cadencia:
    def __init__(self, repo, conversa, relogio, conteudo, hora_inicio=9, hora_fim=20):
        self.repo, self.conversa, self.relogio, self.conteudo = repo, conversa, relogio, conteudo
        self.hora_inicio, self.hora_fim = hora_inicio, hora_fim

    def executar(self, ignorar_horario: bool = False) -> list[Saida]:
        agora = self.relogio.agora()
        if not ignorar_horario and not (self.hora_inicio <= agora.hour < self.hora_fim):
            return []  # fora do horário em que o bot pode puxar conversa
        saidas = []
        for colab in self.repo.colaboradores_para_cadencia():
            dia = jornada.dia_jornada(colab.data_entrada, agora)
            tipo = jornada.tipo_do_dia(dia)
            if tipo and not self.repo.envio_existe(colab.id, dia):
                saidas += self._enviar(colab, dia, tipo)
        return saidas

    def _enviar(self, colab, dia, tipo) -> list[Saida]:
        nome = colab.nome.split()[0]
        agora = self.relogio.agora_str()
        dizer = self.conversa.dizer

        if tipo == "MARCO":
            self.repo.registrar_envio(colab.id, dia, "MARCO", str(dia), agora)
            saidas = [dizer(colab, self.conteudo.marco(dia, nome))]
            gerente = self.repo.gerente_de(colab)
            if gerente:  # lembra a conversa presencial que a empresa já agenda nesses dias
                saidas.append(dizer(gerente, f"📅 {colab.nome} completa {dia} dias hoje. Vale a conversa de acompanhamento prevista para esta data."))
            return saidas

        if tipo == "PILULA":
            p = self.conteudo.proxima_pilula(jornada.semana(dia), self.repo.refs_enviadas(colab.id, "PILULA"))
            if p:
                self.repo.registrar_envio(colab.id, dia, "PILULA", p["id"], agora)
                opcoes = [{"id": f"PIL:{p['id']}:OK", "rotulo": "Entendi ✅"}, {"id": f"PIL:{p['id']}:DUVIDA", "rotulo": "Tenho uma dúvida"}]
                return [dizer(colab, f"💡 Pílula de 30 segundos: {p['titulo']}\n\n{p['texto']}", opcoes)]

        if tipo == "ENQUETE":
            e = self.conteudo.proxima_enquete(self.repo.refs_enviadas(colab.id, "ENQUETE"))
            if e:
                self.repo.registrar_envio(colab.id, dia, "ENQUETE", e["id"], agora)
                opcoes = [{"id": f"ENQ:{e['id']}:{o['id']}", "rotulo": o["rotulo"]} for o in e["opcoes"]]
                return [dizer(colab, e["pergunta"], opcoes)]

        self.repo.registrar_envio(colab.id, dia, "ACOMPANHAMENTO", None, agora)  # sem pílula/enquete sobrando: só conversa
        return [dizer(colab, self.conteudo.acompanhamento(dia, nome))]
