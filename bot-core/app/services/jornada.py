from datetime import date, datetime

MARCOS = (7, 15, 30, 45, 60, 90)  # dias da agenda de conversas que a empresa já tem


def dia_jornada(data_entrada: str | None, agora: datetime) -> int:
    """Dia da jornada (1 = primeiro dia). Retorna 0 para quem não tem data de entrada (gerente, RH...)."""
    if not data_entrada:
        return 0
    return max(1, (agora.date() - date.fromisoformat(data_entrada[:10])).days + 1)


def semana(dia: int) -> int:
    return (dia - 1) // 7 + 1


def _dias_de_contato() -> set:
    dias = set(range(1, 11))                                          # 1-10: todo dia
    dias |= {d for d in range(11, 31) if (d - 10) % 3 == 0}           # 11-30: a cada 3 dias
    dias |= {d for d in range(31, 61) if (d - 30) % 7 == 0}           # 31-60: semanal
    dias |= {d for d in range(61, 91) if (d - 60) % 10 == 0}          # 61-90: a cada 10 dias
    return dias | set(MARCOS)


def _montar_agenda() -> dict:
    """dia -> tipo da mensagem. Poucas pílulas de propósito: o produto é a conversa, não o curso."""
    agenda, n = {}, 0
    for dia in sorted(_dias_de_contato()):
        if dia in MARCOS:
            agenda[dia] = "MARCO"
        elif dia in (2, 5, 8):
            agenda[dia] = "PILULA"
        elif dia == 10:
            agenda[dia] = "ENQUETE"
        elif dia < 10:
            agenda[dia] = "ACOMPANHAMENTO"
        else:
            n += 1
            agenda[dia] = ("PILULA", "ACOMPANHAMENTO", "ENQUETE")[(n - 1) % 3]
    return agenda


AGENDA = _montar_agenda()


def tipo_do_dia(dia: int) -> str | None:
    return AGENDA.get(dia)
