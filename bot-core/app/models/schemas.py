from dataclasses import dataclass, field, asdict
from enum import Enum


class Intencao(str, Enum):
    DUVIDA = "DUVIDA"
    RECLAMACAO = "RECLAMACAO"
    CONVERSA = "CONVERSA"
    ABUSO = "ABUSO"


class Categoria(str, Enum):
    TREINAMENTO = "TREINAMENTO"
    ROTINA = "ROTINA"
    ESCALA = "ESCALA"
    SISTEMAS = "SISTEMAS"
    RELACIONAMENTO = "RELACIONAMENTO"
    SAUDE_BEM_ESTAR = "SAUDE_BEM_ESTAR"
    SEGURANCA = "SEGURANCA"
    OUTRO = "OUTRO"


class Sinal(str, Enum):
    NENHUM = "NENHUM"
    CANSACO = "CANSACO"
    SOBRECARGA = "SOBRECARGA"
    CONFLITO = "CONFLITO"
    DESMOTIVACAO = "DESMOTIVACAO"
    VONTADE_DE_SAIR = "VONTADE_DE_SAIR"
    SITUACAO_GRAVE = "SITUACAO_GRAVE"


class Gravidade(str, Enum):
    BAIXA = "BAIXA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"


class Alvo(str, Enum):
    NENHUM = "NENHUM"
    COLEGA = "COLEGA"
    GERENTE = "GERENTE"
    SISTEMA = "SISTEMA"
    EMPRESA = "EMPRESA"


class Destinatario(str, Enum):
    NENHUM = "NENHUM"
    GERENTE = "GERENTE"
    RH = "RH"


ORDEM_GRAVIDADE = {Gravidade.BAIXA: 0, Gravidade.MEDIA: 1, Gravidade.ALTA: 2}


def _enum(cls, valor, padrao):
    try:
        return cls(str(valor).strip().upper())
    except ValueError:
        return padrao


@dataclass
class ArquivoAudio:
    dados: bytes
    mime: str = "audio/wav"


@dataclass
class Contexto:
    nome: str = "colaborador"
    dia_jornada: int = 1
    resumo: str = ""
    historico: list = field(default_factory=list)  # [(autor, texto)], mais recentes por último

    def para_texto(self) -> str:
        linhas = [f"Nome: {self.nome}", f"Dia da jornada: {self.dia_jornada} de 90",
                  f"Resumo do que já sabemos: {self.resumo or '(nada ainda)'}"]
        if self.historico:
            linhas.append("Últimas mensagens:")
            linhas += [f"- {autor}: {texto}" for autor, texto in self.historico[-6:]]
        return "\n".join(linhas)


@dataclass
class Analise:
    intencao: Intencao = Intencao.CONVERSA
    categoria: Categoria = Categoria.OUTRO
    sinal: Sinal = Sinal.NENHUM
    gravidade: Gravidade = Gravidade.BAIXA
    alvo: Alvo = Alvo.NENHUM
    destinatario: Destinatario = Destinatario.NENHUM
    confianca: float = 0.0
    resposta: str = ""
    transcricao: str | None = None
    sugestao_acao: str | None = None
    resumo_alerta: str | None = None
    resumo_contexto: str | None = None
    origem_analise: str = "gemini"
    escalado_por_regra: bool = False
    aviso: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Analise":
        """Leniente: valores desconhecidos viram o padrão seguro em vez de quebrar."""
        try:
            confianca = max(0.0, min(1.0, float(d.get("confianca", 0.0))))
        except (TypeError, ValueError):
            confianca = 0.0

        def texto(chave):
            v = d.get(chave)
            return v.strip() if isinstance(v, str) and v.strip() else None

        return cls(
            intencao=_enum(Intencao, d.get("intencao"), Intencao.CONVERSA),
            categoria=_enum(Categoria, d.get("categoria"), Categoria.OUTRO),
            sinal=_enum(Sinal, d.get("sinal"), Sinal.NENHUM),
            gravidade=_enum(Gravidade, d.get("gravidade"), Gravidade.BAIXA),
            alvo=_enum(Alvo, d.get("alvo"), Alvo.NENHUM),
            destinatario=_enum(Destinatario, d.get("destinatario"), Destinatario.NENHUM),
            confianca=confianca,
            resposta=texto("resposta") or "Entendi! Me conta mais?",
            transcricao=texto("transcricao"),
            sugestao_acao=texto("sugestao_acao"),
            resumo_alerta=texto("resumo_alerta"),
            resumo_contexto=texto("resumo_contexto"),
        )

    def to_dict(self) -> dict:
        return {k: (v.value if isinstance(v, Enum) else v) for k, v in asdict(self).items()}
