"""Leitura e cadastro para o painel do RH. Regras de privacidade:
- o RH só enxerga alertas que o colaborador CONFIRMOU (nada de 'aguardando confirmação' ou 'só contexto');
- o resumo do alerta só aparece para o canal RH (o do gerente fica com o gerente);
- a conversa em si nunca vai para o painel."""
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from app.services import jornada
from app.services.relogio import FORMATO

ABERTOS = ("ABERTO", "SEM_RESPOSTA_24H", "NAO_CONSEGUIU")
VISIVEIS = ABERTOS + ("ATENDIDO",)
PAPEIS = ("COLABORADOR", "GERENTE", "MENTOR", "RH")
SINAL_ROTULO = {"CANSACO": "cansaço", "SOBRECARGA": "sobrecarga", "CONFLITO": "conflito", "DESMOTIVACAO": "desmotivação",
                "VONTADE_DE_SAIR": "vontade de sair", "SITUACAO_GRAVE": "situação grave", "NENHUM": "acompanhamento"}
ESTADO_ROTULO = {"ABERTO": "Aguardando líder", "SEM_RESPOSTA_24H": "Sem resposta 24h",
                 "NAO_CONSEGUIU": "Líder não conseguiu", "ATENDIDO": "Atendido"}
CATEGORIA = {"ABERTO": "open", "SEM_RESPOSTA_24H": "no-response", "NAO_CONSEGUIU": "not-reached", "ATENDIDO": "attended"}
PRIORIDADE = {"no-response": 0, "not-reached": 1, "open": 2, "attended": 3}


class Conflito(Exception):
    """Cadastro que bate com algo que já existe (ex.: telefone repetido)."""


def _dt(texto):
    return datetime.strptime(texto, FORMATO) if texto else None


def _rotulo_data(dt, agora):
    if dt.date() == agora.date():
        return f"Hoje, {dt:%H:%M}"
    if dt.date() == (agora - timedelta(days=1)).date():
        return f"Ontem, {dt:%H:%M}"
    return f"{dt:%d/%m}, {dt:%H:%M}"


def _telefone(valor) -> str:
    digitos = re.sub(r"\D", "", str(valor or ""))
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    if not 12 <= len(digitos) <= 13:
        raise ValueError("Telefone inválido. Use DDD + número, por exemplo 51 99999-0000.")
    return digitos


class Painel:
    def __init__(self, repo, relogio, conteudo):
        self.repo, self.relogio, self.conteudo = repo, relogio, conteudo
        self.b = repo.b

    # ---------- consultas base ----------
    def _pessoas(self):
        return [dict(r) for r in self.b.todos(
            "SELECT c.*, l.nome AS loja, g.nome AS gerente_nome FROM colaborador c"
            " LEFT JOIN loja l ON l.id=c.loja_id LEFT JOIN colaborador g ON g.id=c.gerente_id"
            " WHERE c.ativo=1 ORDER BY c.nome")]

    def _mentores_ativos(self):
        rows = self.b.todos("SELECT m.id, m.mentor_id, m.aprendiz_id, c.nome AS mentor_nome FROM mentoria m"
                            " JOIN colaborador c ON c.id=m.mentor_id WHERE m.fim IS NULL")
        return {r["aprendiz_id"]: dict(r) for r in rows}

    def _alertas(self):
        marcas = ",".join("?" * len(VISIVEIS))
        return [dict(r) for r in self.b.todos(
            "SELECT a.*, c.nome AS colab_nome, l.nome AS loja, d.nome AS dest_nome FROM alerta a"
            " JOIN colaborador c ON c.id=a.colaborador_id LEFT JOIN loja l ON l.id=c.loja_id"
            f" LEFT JOIN colaborador d ON d.id=a.destinatario_id WHERE a.estado IN ({marcas})"
            " ORDER BY COALESCE(a.confirmado_em, a.criado_em) DESC", VISIVEIS)]

    def lojas(self):
        return [dict(r) for r in self.b.todos("SELECT id, nome FROM loja ORDER BY nome")]

    @staticmethod
    def _status(p, alertas, agora):
        estados = {a["estado"] for a in alertas}
        if "SEM_RESPOSTA_24H" in estados:
            return "no-response", "Sem resposta 24h"
        if "NAO_CONSEGUIU" in estados:
            return "open-alert", "Líder não conseguiu"
        if "ABERTO" in estados:
            return "open-alert", "Alerta aberto"
        if not p["consentimento_em"]:
            return "pending", "Aguardando aceite"
        if p["optout_em"]:
            return "paused", "Pausado"
        if any(a["estado"] == "ATENDIDO" and a["retorno_em"] and agora - _dt(a["retorno_em"]) <= timedelta(days=7)
               for a in alertas):
            return "attended", "Atendido"
        return "on-track", "Em dia"

    # ---------- visão geral ----------
    def dashboard(self):
        agora = self.relogio.agora()
        alertas = self._alertas()
        por_pessoa = defaultdict(list)
        for a in alertas:
            por_pessoa[a["colaborador_id"]].append(a)
        mentores = self._mentores_ativos()
        jornadas, na_jornada = [], 0
        for p in self._pessoas():
            if p["papel"] != "COLABORADOR":
                continue
            dia = jornada.dia_jornada(p["data_entrada"], agora)
            if not 1 <= dia <= 90:
                continue
            status, rotulo = self._status(p, por_pessoa.get(p["id"], []), agora)
            na_jornada += 1 if p["consentimento_em"] else 0
            m = mentores.get(p["id"])
            jornadas.append({"id": p["id"], "employeeName": p["nome"], "store": p["loja"] or "-", "day": dia, "totalDays": 90,
                             "status": status, "statusLabel": rotulo, "mentor": m["mentor_nome"] if m else None,
                             "manager": p["gerente_nome"]})
        ordem = {"no-response": 0, "open-alert": 1, "pending": 2, "paused": 3, "attended": 4, "on-track": 5}
        jornadas.sort(key=lambda j: (ordem[j["status"]], j["employeeName"]))
        lista = self.alertas_lista(alertas, agora)
        resumo = {"inJourney": na_jornada,
                  "openAlerts": sum(1 for a in alertas if a["estado"] in ABERTOS),
                  "noResponse": sum(1 for a in alertas if a["estado"] == "SEM_RESPOSTA_24H"),
                  "attended": sum(1 for a in alertas if a["estado"] == "ATENDIDO")}
        lojas = self.lojas()
        return {"summary": resumo, "journeys": jornadas, "alerts": lista, "stores": [l["nome"] for l in lojas],
                "storeList": lojas}

    def alertas_lista(self, alertas, agora):
        saida = []
        for a in alertas:
            cat = CATEGORIA[a["estado"]]
            saida.append({"id": a["id"], "colaboradorId": a["colaborador_id"], "employeeName": a["colab_nome"],
                          "store": a["loja"] or "-", "signal": SINAL_ROTULO.get(a["sinal"], "acompanhamento"),
                          "recommendation": a["sugestao"] or "", "state": ESTADO_ROTULO[a["estado"]], "category": cat,
                          "createdAt": _rotulo_data(_dt(a["confirmado_em"] or a["criado_em"]), agora),
                          "channel": a["canal"], "owner": a["dest_nome"], "severity": a["gravidade"],
                          "summary": a["resumo"] if a["canal"] == "RH" else None})  # privacidade: só o canal RH mostra o resumo
        saida.sort(key=lambda x: PRIORIDADE[x["category"]])  # estável: mantém a ordem por data dentro de cada grupo
        return saida

    # ---------- colaboradores ----------
    def colaboradores(self):
        agora = self.relogio.agora()
        mentores = self._mentores_ativos()
        saida = []
        for p in self._pessoas():
            dia = jornada.dia_jornada(p["data_entrada"], agora)
            m = mentores.get(p["id"])
            saida.append({"id": p["id"], "nome": p["nome"], "telefone": p["telefone"], "lojaId": p["loja_id"], "loja": p["loja"],
                          "papel": p["papel"], "dataEntrada": p["data_entrada"], "dia": dia or None,
                          "gerenteId": p["gerente_id"], "gerente": p["gerente_nome"],
                          "mentorId": m["mentor_id"] if m else None, "mentor": m["mentor_nome"] if m else None,
                          "aceitou": bool(p["consentimento_em"]), "pausado": bool(p["optout_em"])})
        return saida

    def _colaborador(self, id_):
        c = next((c for c in self.colaboradores() if c["id"] == id_), None)
        if not c:
            raise LookupError("colaborador não encontrado")
        return c

    def _gerente_valido(self, gerente_id):
        g = self.repo.colaborador(gerente_id)
        if not g or not g.ativo or g.papel != "GERENTE":
            raise ValueError("O gerente escolhido não existe ou não tem o papel de gerente.")
        return g

    def criar_colaborador(self, dados: dict):
        nome = str(dados.get("nome") or "").strip()
        if len(nome) < 2:
            raise ValueError("Informe o nome.")
        papel = str(dados.get("papel") or "COLABORADOR").upper()
        if papel not in PAPEIS:
            raise ValueError("Papel inválido.")
        telefone = _telefone(dados.get("telefone"))
        if self.repo.colaborador_por_telefone(telefone):
            raise Conflito("Já existe alguém cadastrado com esse telefone.")
        loja_id = dados.get("lojaId")
        if papel != "RH" and not loja_id:
            raise ValueError("Escolha a loja.")
        if loja_id and not self.b.um("SELECT 1 FROM loja WHERE id=?", (loja_id,)):
            raise ValueError("Loja não encontrada.")
        entrada = dados.get("dataEntrada") or None
        if papel == "COLABORADOR":
            try:
                data = datetime.strptime(str(entrada), "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("Informe a data de entrada (AAAA-MM-DD).")
            if data > self.relogio.agora().date():
                raise ValueError("A data de entrada não pode estar no futuro.")
        gerente_id = dados.get("gerenteId")
        if papel == "COLABORADOR":
            if gerente_id:
                self._gerente_valido(gerente_id)
            else:  # padrão: o gerente da loja
                g = self.b.um("SELECT id FROM colaborador WHERE papel='GERENTE' AND ativo=1 AND loja_id=? ORDER BY id LIMIT 1", (loja_id,))
                gerente_id = g["id"] if g else None
        else:
            gerente_id = None
        novo = self.repo.criar_colaborador(nome, telefone, loja_id, papel, entrada if papel == "COLABORADOR" else None, gerente_id)
        return self._colaborador(novo)

    def atualizar_colaborador(self, id_: int, dados: dict):
        atual = self._colaborador(id_)
        if "nome" in dados:
            nome = str(dados["nome"] or "").strip()
            if len(nome) < 2:
                raise ValueError("Informe o nome.")
            self.b.exec("UPDATE colaborador SET nome=? WHERE id=?", (nome, id_))
        if "lojaId" in dados:
            if dados["lojaId"] and not self.b.um("SELECT 1 FROM loja WHERE id=?", (dados["lojaId"],)):
                raise ValueError("Loja não encontrada.")
            self.b.exec("UPDATE colaborador SET loja_id=? WHERE id=?", (dados["lojaId"], id_))
        if "gerenteId" in dados:
            if dados["gerenteId"]:
                self._gerente_valido(dados["gerenteId"])
            self.b.exec("UPDATE colaborador SET gerente_id=? WHERE id=?", (dados["gerenteId"], id_))
        if dados.get("ativo") is False:
            self.b.exec("UPDATE colaborador SET ativo=0 WHERE id=?", (id_,))
            self.b.exec("UPDATE mentoria SET fim=? WHERE fim IS NULL AND (mentor_id=? OR aprendiz_id=?)",
                        (self.relogio.agora_str(), id_, id_))
            return {**atual, "ativo": False}
        return self._colaborador(id_)

    # ---------- mentoria ----------
    def mentorias(self):
        agora = self.relogio.agora()
        vinculos = [dict(r) for r in self.b.todos(
            "SELECT m.id, m.mentor_id, m.aprendiz_id, m.inicio, mc.nome AS mentor, ac.nome AS aprendiz, ac.data_entrada,"
            " l.nome AS loja FROM mentoria m JOIN colaborador mc ON mc.id=m.mentor_id JOIN colaborador ac ON ac.id=m.aprendiz_id"
            " LEFT JOIN loja l ON l.id=ac.loja_id WHERE m.fim IS NULL AND ac.ativo=1 AND mc.ativo=1 ORDER BY mc.nome, ac.nome")]
        por_mentor = Counter(v["mentor_id"] for v in vinculos)
        com_mentor = {v["aprendiz_id"] for v in vinculos}
        mentores = [{"id": p["id"], "nome": p["nome"], "loja": p["loja"], "aprendizes": por_mentor.get(p["id"], 0)}
                    for p in self._pessoas() if p["papel"] == "MENTOR"]
        sem_mentor = []
        for p in self._pessoas():
            dia = jornada.dia_jornada(p["data_entrada"], agora)
            if p["papel"] == "COLABORADOR" and 1 <= dia <= 90 and p["id"] not in com_mentor:
                sem_mentor.append({"id": p["id"], "nome": p["nome"], "loja": p["loja"], "dia": dia})
        return {"vinculos": [{"id": v["id"], "mentorId": v["mentor_id"], "mentor": v["mentor"], "aprendizId": v["aprendiz_id"],
                              "aprendiz": v["aprendiz"], "loja": v["loja"], "dia": jornada.dia_jornada(v["data_entrada"], agora),
                              "desde": v["inicio"][:10]} for v in vinculos],
                "mentores": mentores, "semMentor": sem_mentor}

    def vincular(self, mentor_id: int, aprendiz_id: int):
        mentor, aprendiz = self.repo.colaborador(mentor_id), self.repo.colaborador(aprendiz_id)
        if not mentor or not mentor.ativo or mentor.papel != "MENTOR":
            raise ValueError("Escolha uma pessoa com o papel de mentor.")
        if not aprendiz or not aprendiz.ativo or aprendiz.papel != "COLABORADOR":
            raise ValueError("Escolha um colaborador em jornada como aprendiz.")
        agora = self.relogio.agora_str()
        self.b.exec("UPDATE mentoria SET fim=? WHERE aprendiz_id=? AND fim IS NULL", (agora, aprendiz_id))  # um mentor por aprendiz
        self.b.exec("INSERT INTO mentoria(mentor_id, aprendiz_id, inicio) VALUES (?,?,?)", (mentor_id, aprendiz_id, agora))
        return self.mentorias()

    def encerrar_mentoria(self, id_: int):
        if not self.b.um("SELECT 1 FROM mentoria WHERE id=? AND fim IS NULL", (id_,)):
            raise LookupError("vínculo não encontrado")
        self.b.exec("UPDATE mentoria SET fim=? WHERE id=?", (self.relogio.agora_str(), id_))
        return self.mentorias()

    # ---------- insights ----------
    def insights(self):
        agora = self.relogio.agora()
        alertas = self._alertas()

        sinais = Counter(SINAL_ROTULO.get(a["sinal"], "acompanhamento") for a in alertas)
        segunda = agora.date() - timedelta(days=agora.weekday())
        semanas = [segunda - timedelta(weeks=i) for i in range(5, -1, -1)]
        contagem = Counter()
        for a in alertas:
            d = _dt(a["confirmado_em"] or a["criado_em"]).date()
            contagem[d - timedelta(days=d.weekday())] += 1
        por_semana = [{"semana": s.strftime("%d/%m"), "total": contagem.get(s, 0)} for s in semanas]

        horas = [(_dt(a["retorno_em"]) - _dt(a["confirmado_em"] or a["criado_em"])).total_seconds() / 3600
                 for a in alertas if a["retorno_em"]]
        tempo_medio = round(sum(horas) / len(horas), 1) if horas else None
        em_24h = round(100 * sum(1 for h in horas if h <= 24) / len(horas)) if horas else None

        base = self.b.um(
            "SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN EXISTS(SELECT 1 FROM mensagem m WHERE m.colaborador_id=c.id"
            " AND m.direcao='ENTRADA' AND m.dia_jornada<=10) OR EXISTS(SELECT 1 FROM enquete_resposta e WHERE e.colaborador_id=c.id"
            " AND e.dia_jornada<=10) THEN 1 ELSE 0 END), 0) AS resp FROM colaborador c WHERE c.papel='COLABORADOR' AND c.ativo=1"
            " AND c.consentimento_em IS NOT NULL")
        taxa = round(100 * base["resp"] / base["total"]) if base["total"] else None

        contagens = {(r["enquete_id"], r["opcao_id"]): r["n"] for r in self.repo.contar_respostas_enquete()}
        enquetes = []
        for e in self.conteudo.enquetes:
            total = sum(contagens.get((e["id"], o["id"]), 0) for o in e["opcoes"])
            if total:
                enquetes.append({"id": e["id"], "pergunta": e["pergunta"], "tema": e["tema"], "total": total,
                                 "opcoes": [{"id": o["id"], "rotulo": o["rotulo"], "n": contagens.get((e["id"], o["id"]), 0),
                                             "pct": round(100 * contagens.get((e["id"], o["id"]), 0) / total)} for o in e["opcoes"]]})
        c = {o: contagens.get(("curso-x-loja", o), 0) for o in ("igual", "parte", "diferente", "sem-curso")}
        m = self.mentorias()
        return {"taxaResposta10Dias": {"valor": taxa, "meta": 50, "base": base["total"]},
                "tempoMedioRetornoHoras": tempo_medio, "atendidosEm24hPct": em_24h,
                "totalAlertas": len(alertas),
                "sinais": [{"rotulo": k, "n": v} for k, v in sinais.most_common()],
                "alertasPorSemana": por_semana, "enquetes": enquetes,
                "treinamento": {"total": sum(c.values()), "bate": c["igual"], "emParte": c["parte"], "diferente": c["diferente"],
                                "semCurso": c["sem-curso"]},
                "mentoria": {"comMentor": len(m["vinculos"]), "semMentor": len(m["semMentor"])}}
