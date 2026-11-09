"""Rede de proteção: regras de palavras-chave que corrigem a IA quando ela deixa passar algo grave.
Nunca rebaixa uma classificação, só escala."""
import re

from app.models.schemas import Analise, Categoria, Destinatario, Gravidade, Sinal, ORDEM_GRAVIDADE

CRISE = [r"me matar", r"suic[ií]d", r"n[aã]o quero mais viver", r"acabar com (a )?minha vida", r"tirar (a )?minha vida"]
RH = [r"ass[eé]dio", r"assedi", r"machist", r"racis", r"preconceito", r"humilh", r"me chamou de (burr|idiot|incompetent)",
      r"ameaç", r"me tocou", r"encostou em mim", r"vale[- ]transporte", r"bater (o )?ponto e (continu|voltar)",
      r"\broubo\b", r"dinheiro do caixa", r"denunciar"]
RISCO_FISICO = [r"\bchoque\b", r"vazando", r"vazamento", r"escorreg", r"me queimei", r"queimadura", r"me cortei",
                r"fio solto", r"cheiro de g[aá]s"]

# "não teve assédio", "sem assédio": a palavra aparece, mas negada.
_NEGACAO = re.compile(r"(n[aã]o|nunca)\s+(teve|tem|houve|existe|rolou|sofri|sofro|vi)\s+(\w+\s+){0,2}$|\bsem\s+(\w+\s+){0,1}$", re.I)

RESPOSTA_CRISE = ("Sinto muito que você esteja se sentindo assim, e fico feliz que tenha me contado. Você não precisa passar por isso sozinho(a). "
                  "Se estiver em perigo agora, ligue 192 (SAMU). O CVV atende 24 horas pelo 188, de graça. "
                  "Posso avisar o RH para alguém conversar com você com todo o cuidado? Só aviso com o seu ok.")


def _achou(padroes, texto: str, negavel: bool = True) -> bool:
    for padrao in padroes:
        for m in re.finditer(padrao, texto, re.I):
            if negavel and _NEGACAO.search(texto[max(0, m.start() - 40):m.start()]):
                continue
            return True
    return False


def _subir_gravidade(a: Analise, minimo: Gravidade):
    if ORDEM_GRAVIDADE[a.gravidade] < ORDEM_GRAVIDADE[minimo]:
        a.gravidade = minimo


def _confirmar(a: Analise, pergunta: str):
    a.resposta = (a.resposta.rstrip() + " " + pergunta).strip()


def aplicar(a: Analise, texto: str | None) -> Analise:
    t = texto or a.transcricao or ""
    if not t:
        return a

    if _achou(CRISE, t, negavel=False):  # sem checagem de negação: na dúvida, acolhe
        a.sinal, a.gravidade, a.destinatario = Sinal.SITUACAO_GRAVE, Gravidade.ALTA, Destinatario.RH
        a.categoria = Categoria.SAUDE_BEM_ESTAR
        a.resposta = RESPOSTA_CRISE
        a.sugestao_acao = a.sugestao_acao or "contato humano ainda hoje, com sigilo e cuidado"
        a.resumo_alerta = a.resumo_alerta or "O colaborador relatou pensamentos de se machucar."
        a.escalado_por_regra = True
    elif _achou(RH, t) and a.destinatario != Destinatario.RH:
        a.destinatario = Destinatario.RH
        if a.sinal == Sinal.NENHUM:
            a.sinal = Sinal.SITUACAO_GRAVE
        _subir_gravidade(a, Gravidade.ALTA)
        _confirmar(a, "Posso avisar o RH? Eles tratam isso com sigilo, e só aviso com o seu ok.")
        a.escalado_por_regra = True
    elif _achou(RISCO_FISICO, t) and a.destinatario == Destinatario.NENHUM:
        a.destinatario = Destinatario.GERENTE
        if a.sinal == Sinal.NENHUM:
            a.sinal = Sinal.SITUACAO_GRAVE
        a.categoria = Categoria.SEGURANCA
        _subir_gravidade(a, Gravidade.ALTA)
        _confirmar(a, "Posso avisar o seu gerente agora para resolverem isso? Só aviso com o seu ok.")
        a.escalado_por_regra = True
    return a
