"""Fluxo da conversa: aceite, mensagens, confirmação, alerta, retorno do líder e lembrete de 24h.
Não conhece HTTP: recebe pedidos e devolve 'Saidas' (mensagens a entregar a cada telefone)."""
import re
from dataclasses import dataclass

from app.models.schemas import ArquivoAudio, Contexto, Destinatario
from app.services import jornada
from app.services.conteudo import Conteudo

OPCOES_ACEITE = [{"id": "ACEITO", "rotulo": "Quero participar"}, {"id": "AGORA_NAO", "rotulo": "Agora não"}]
OPCOES_CONFIRMA = [{"id": "AVISAR", "rotulo": "Pode avisar"}, {"id": "NAO_AVISAR", "rotulo": "Prefiro que não"}]
OPCOES_RETORNO = [{"id": "CONVERSEI", "rotulo": "Conversei"}, {"id": "NAO_CONSEGUIU", "rotulo": "Não consegui"}]

BOAS_VINDAS = (
    "Oi, {nome}! Eu sou o Parceiro dos 90 dias 👋\n"
    "Vou te mandar mensagens curtas, dicas e tirar dúvidas sobre o trabalho.\n\n"
    "Transparência: se você me contar algo que merece atenção, eu aviso o seu gerente (ou o RH, se for algo mais sensível) "
    "e SEMPRE te pergunto antes. Participar é opcional e você pode escrever “parar” quando quiser."
)
_SIM = re.compile(r"^(sim|s|pode|pode sim|pode avisar|ok|claro|tudo bem|autorizo|quero|aceito|bora)\b", re.I)
_NAO = re.compile(r"^(n[aã]o|n|prefiro que n[aã]o|melhor n[aã]o|nem)\b", re.I)


@dataclass
class Saida:
    para: str  # telefone
    texto: str
    opcoes: list | None = None
    alerta_id: int | None = None

    def para_evento(self) -> dict:
        ev = {"tipo": "botoes" if self.opcoes else "texto", "texto": self.texto}
        if self.opcoes:
            ev["opcoes"] = self.opcoes
        if self.alerta_id:
            ev["alertaId"] = self.alerta_id
        return ev


def _primeiro_nome(colab) -> str:
    return colab.nome.split()[0]


def _resposta_confirmacao(texto: str) -> bool | None:
    t = (texto or "").strip()
    if len(t.split()) > 5:
        return None
    if _SIM.match(t):
        return True
    if _NAO.match(t):
        return False
    return None


class Conversa:
    def __init__(self, repo, analisador, relogio, conteudo=None):
        self.repo, self.analisador, self.relogio = repo, analisador, relogio
        self.conteudo = conteudo or Conteudo.carregar()

    # ---------- utilidades ----------
    def _dia(self, colab) -> int:
        return jornada.dia_jornada(colab.data_entrada, self.relogio.agora())

    def dizer(self, colab, texto, opcoes=None, alerta_id=None) -> Saida:
        self.repo.salvar_mensagem(colab.id, "SAIDA", "TEXTO", texto, None, self._dia(colab), self.relogio.agora_str())
        return Saida(colab.telefone, texto, opcoes, alerta_id)

    # ---------- entrada: primeiro contato ----------
    def boas_vindas_se_preciso(self, telefone: str) -> list[Saida]:
        colab = self.repo.colaborador_por_telefone(telefone)
        if not colab or colab.papel != "COLABORADOR" or colab.consentimento_em or colab.optout_em:
            return []
        if self.repo.tem_mensagem_saida(colab.id):
            return []
        return [self.dizer(colab, BOAS_VINDAS.format(nome=_primeiro_nome(colab)), OPCOES_ACEITE)]

    # ---------- entrada: texto ou áudio ----------
    def processar_texto(self, telefone: str, texto: str | None = None, audio: ArquivoAudio | None = None,
                        origem: str = "TEXTO") -> list[Saida]:
        colab = self.repo.colaborador_por_telefone(telefone)
        if not colab or not colab.ativo:
            return [Saida(telefone, "Não encontrei o seu cadastro. Fale com o seu gerente para ser incluído(a).")]
        if colab.papel != "COLABORADOR":
            return [self.dizer(colab, "Por aqui eu aviso quando alguém precisar de atenção. É só usar os botões dos alertas. 🙂")]

        comando = (texto or "").strip().lower()
        if comando in ("parar", "pausar", "sair"):
            self.repo.marcar_optout(colab.id, self.relogio.agora_str())
            return [self.dizer(colab, "Tudo bem, vou pausar por aqui. Quando quiser voltar, escreva “voltar”. 👋")]
        if colab.optout_em:
            if comando in ("voltar", "retomar"):
                self.repo.retomar(colab.id)
                return [self.dizer(colab, "Que bom te ver de volta! Como você está hoje?")]
            return [self.dizer(colab, "O acompanhamento está pausado. Escreva “voltar” quando quiser retomar.")]

        if not colab.consentimento_em:
            if _resposta_confirmacao(texto or "") is True:
                return self._aceitar(colab)
            return [self.dizer(colab, "Antes de começarmos, preciso do seu ok para conversar por aqui.", OPCOES_ACEITE)]

        pendente = self.repo.alerta_pendente(colab.id)
        if pendente and texto:
            decisao = _resposta_confirmacao(texto)
            if decisao is True:
                return self._confirmar(colab, pendente)
            if decisao is False:
                return self._recusar(colab, pendente)

        return self._analisar(colab, texto, audio, origem)

    def _analisar(self, colab, texto, audio, origem) -> list[Saida]:
        dia = self._dia(colab)
        contexto = Contexto(nome=_primeiro_nome(colab), dia_jornada=dia, resumo=colab.resumo_contexto,
                            historico=self.repo.ultimas_mensagens(colab.id))
        analise = self.analisador.analisar(texto=texto, audio=audio, contexto=contexto)
        msg_id = self.repo.salvar_mensagem(colab.id, "ENTRADA", origem, texto, analise.transcricao, dia,
                                           self.relogio.agora_str())
        analise_id = self.repo.salvar_analise(msg_id, analise)
        if analise.resumo_contexto:
            self.repo.atualizar_resumo(colab.id, analise.resumo_contexto)

        if analise.destinatario == Destinatario.NENHUM:
            return [self.dizer(colab, analise.resposta)]

        self.repo.descartar_pendentes(colab.id)
        self.repo.criar_alerta(colab.id, analise_id, analise.destinatario.value, analise.sinal.value,
                               analise.gravidade.value, analise.sugestao_acao, analise.resumo_alerta,
                               "AGUARDANDO_CONFIRMACAO", self.relogio.agora_str())
        return [self.dizer(colab, analise.resposta, OPCOES_CONFIRMA)]

    # ---------- entrada: botões ----------
    def processar_escolha(self, telefone: str, opcao_id: str) -> list[Saida]:
        colab = self.repo.colaborador_por_telefone(telefone)
        if not colab or colab.papel != "COLABORADOR":
            return []
        if opcao_id == "ACEITO":
            return self._aceitar(colab)
        if opcao_id.startswith(("PIL:", "ENQ:")):
            return self._escolha_conteudo(colab, opcao_id)
        if opcao_id == "AGORA_NAO":
            return [self.dizer(colab, "Tudo bem! Se mudar de ideia, é só me escrever. 🙂")]
        pendente = self.repo.alerta_pendente(colab.id)
        if opcao_id == "AVISAR" and pendente:
            return self._confirmar(colab, pendente)
        if opcao_id == "NAO_AVISAR" and pendente:
            return self._recusar(colab, pendente)
        return []

    def _aceitar(self, colab) -> list[Saida]:
        self.repo.marcar_consentimento(colab.id, self.relogio.agora_str())
        self.repo.registrar_envio(colab.id, self._dia(colab), "ACEITE", None, self.relogio.agora_str())  # hoje já conversamos
        return [self.dizer(colab, f"Show, {_primeiro_nome(colab)}! Daqui pra frente eu te mando umas mensagens curtas por aqui. "
                                   "Como foi o seu dia hoje?")]

    # ---------- respostas a pílulas e enquetes ----------
    def _escolha_conteudo(self, colab, opcao_id) -> list[Saida]:
        partes = opcao_id.split(":", 2)
        if len(partes) != 3:
            return []
        tipo, ref, escolha = partes
        if tipo == "PIL":
            if escolha == "OK":
                self.repo.concluir_envio(colab.id, "PILULA", ref, self.relogio.agora_str())
                return [self.dizer(colab, "Boa! Se bater alguma dúvida na prática, é só me chamar. 🙌")]
            return [self.dizer(colab, "Pode mandar a sua dúvida por aqui. Se eu não souber, sugiro falar com o seu gerente. 😉")]
        enquete = self.conteudo.enquete(ref)
        opcao = next((o for o in (enquete or {}).get("opcoes", []) if o["id"] == escolha), None)
        if not opcao:
            return []
        self.repo.salvar_resposta_enquete(ref, colab.id, opcao["id"], opcao["rotulo"], self._dia(colab), self.relogio.agora_str())
        if not opcao.get("sinal"):
            return [self.dizer(colab, enquete.get("resposta") or "Valeu por responder! 🙌")]
        self.repo.descartar_pendentes(colab.id)
        self.repo.criar_alerta(colab.id, None, "GERENTE", opcao["sinal"], "MEDIA", opcao.get("sugestao"),
                               f"Na enquete \"{enquete['pergunta']}\", a pessoa respondeu \"{opcao['rotulo']}\".",
                               "AGUARDANDO_CONFIRMACAO", self.relogio.agora_str())
        return [self.dizer(colab, "Obrigado por contar! Parece que não está fácil. Posso avisar o seu gerente para vocês conversarem? "
                                  "Só aviso com o seu ok.", OPCOES_CONFIRMA)]

    # ---------- confirmação do colaborador ----------
    def _recusar(self, colab, alerta) -> list[Saida]:
        self.repo.atualizar_alerta(alerta.id, estado="SO_CONTEXTO")
        return [self.dizer(colab, "Tudo bem, não vou avisar ninguém. Se mudar de ideia, é só me falar. 🙂")]

    def _confirmar(self, colab, alerta) -> list[Saida]:
        destino = self.repo.rh() if alerta.canal == "RH" else self.repo.gerente_de(colab)
        self.repo.atualizar_alerta(alerta.id, estado="ABERTO", confirmado_em=self.relogio.agora_str(),
                                   lembrete_em=self.relogio.em(24), destinatario_id=destino.id if destino else None)
        quem = "o RH, que vai tratar com sigilo e cuidado" if alerta.canal == "RH" else "o seu gerente"
        saidas = [self.dizer(colab, f"Combinado! Avisei {quem}. Se alguém te procurar, é por causa disso. 💬")]
        if destino:
            saidas.append(self.dizer(destino, self._texto_alerta(colab, alerta), OPCOES_RETORNO, alerta.id))
        return saidas

    def _texto_alerta(self, colab, alerta, lembrete=False) -> str:
        sugestao = alerta.sugestao or "vale uma conversa nos próximos dias"
        resumo = alerta.resumo or "A pessoa pediu atenção sobre o dia a dia."
        topo = "⏰ Lembrete: ainda sem retorno sobre" if lembrete else ("🔒 Relato sensível de" if alerta.canal == "RH" else "🔔 Alerta sobre")
        return f"{topo} {colab.nome} (dia {self._dia(colab)}).\n{resumo}\nSugestão: {sugestao}."

    # ---------- retorno de quem recebeu o alerta ----------
    def registrar_retorno(self, alerta_id: int, resultado: str) -> list[Saida]:
        resultado = (resultado or "").upper()
        if resultado not in ("CONVERSEI", "NAO_CONSEGUIU"):
            raise ValueError("resultado deve ser CONVERSEI ou NAO_CONSEGUIU")
        alerta = self.repo.alerta(alerta_id)
        if not alerta:
            raise LookupError("alerta não encontrado")
        destino = self.repo.colaborador(alerta.destinatario_id) if alerta.destinatario_id else None
        if alerta.estado not in ("ABERTO", "SEM_RESPOSTA_24H", "NAO_CONSEGUIU"):
            return [self.dizer(destino, "Esse alerta já foi encerrado. 👍")] if destino else []
        estado = "ATENDIDO" if resultado == "CONVERSEI" else "NAO_CONSEGUIU"
        self.repo.atualizar_alerta(alerta_id, estado=estado, retorno_em=self.relogio.agora_str())
        if not destino:
            return []
        texto = "Registrado ✅ Obrigado por cuidar disso!" if estado == "ATENDIDO" else \
            "Registrado. Quando conseguir, vale tentar de novo. 👍"
        return [self.dizer(destino, texto)]

    # ---------- lembrete manual (botão "Reenviar lembrete" do painel do RH) ----------
    def reenviar_lembrete(self, alerta_id: int) -> list[Saida]:
        alerta = self.repo.alerta(alerta_id)
        if not alerta:
            raise LookupError("alerta não encontrado")
        if alerta.estado not in ("ABERTO", "SEM_RESPOSTA_24H", "NAO_CONSEGUIU"):
            raise ValueError("esse alerta já foi encerrado ou ainda não foi confirmado pelo colaborador")
        destino = self.repo.colaborador(alerta.destinatario_id) if alerta.destinatario_id else None
        colab = self.repo.colaborador(alerta.colaborador_id)
        if not destino or not colab:
            raise ValueError("esse alerta não tem um destinatário no WhatsApp")
        self.repo.atualizar_alerta(alerta.id, lembrado_em=self.relogio.agora_str())  # evita o lembrete automático repetido
        return [self.dizer(destino, self._texto_alerta(colab, alerta, lembrete=True), OPCOES_RETORNO, alerta.id)]

    # ---------- lembrete de 24h ----------
    def processar_lembretes(self) -> list[Saida]:
        saidas = []
        for alerta in self.repo.alertas_para_lembrar(self.relogio.agora_str()):
            self.repo.atualizar_alerta(alerta.id, estado="SEM_RESPOSTA_24H", lembrado_em=self.relogio.agora_str())
            destino = self.repo.colaborador(alerta.destinatario_id) if alerta.destinatario_id else None
            colab = self.repo.colaborador(alerta.colaborador_id)
            if destino and colab:
                saidas.append(self.dizer(destino, self._texto_alerta(colab, alerta, lembrete=True), OPCOES_RETORNO, alerta.id))
        return saidas
