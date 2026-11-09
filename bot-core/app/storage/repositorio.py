from types import SimpleNamespace

ESTADOS_ABERTOS = ("ABERTO", "SEM_RESPOSTA_24H", "NAO_CONSEGUIU")
_CAMPOS_ALERTA = {"estado", "destinatario_id", "confirmado_em", "lembrete_em", "lembrado_em", "retorno_em"}


def _obj(row):
    return SimpleNamespace(**dict(row)) if row else None


class Repositorio:
    def __init__(self, banco):
        self.b = banco

    # ---- lojas e pessoas ----
    def criar_loja(self, nome):
        self.b.exec("INSERT OR IGNORE INTO loja(nome) VALUES (?)", (nome,))
        return self.b.um("SELECT id FROM loja WHERE nome=?", (nome,))["id"]

    def criar_colaborador(self, nome, telefone, loja_id=None, papel="COLABORADOR", data_entrada=None,
                          gerente_id=None, consentimento_em=None):
        cur = self.b.exec(
            "INSERT INTO colaborador(nome, telefone, loja_id, papel, data_entrada, gerente_id, consentimento_em)"
            " VALUES (?,?,?,?,?,?,?)", (nome, telefone, loja_id, papel, data_entrada, gerente_id, consentimento_em))
        return cur.lastrowid

    def tem_dados(self):
        return self.b.um("SELECT COUNT(*) AS n FROM colaborador")["n"] > 0

    def colaborador(self, id_):
        return _obj(self.b.um("SELECT * FROM colaborador WHERE id=?", (id_,)))

    def colaborador_por_telefone(self, telefone):
        return _obj(self.b.um("SELECT * FROM colaborador WHERE telefone=?", (telefone,)))

    def gerente_de(self, colab):
        return self.colaborador(colab.gerente_id) if colab.gerente_id else None

    def rh(self):
        return _obj(self.b.um("SELECT * FROM colaborador WHERE papel='RH' AND ativo=1 ORDER BY id LIMIT 1"))

    def marcar_consentimento(self, id_, quando):
        self.b.exec("UPDATE colaborador SET consentimento_em=?, optout_em=NULL WHERE id=?", (quando, id_))

    def marcar_optout(self, id_, quando):
        self.b.exec("UPDATE colaborador SET optout_em=? WHERE id=?", (quando, id_))

    def retomar(self, id_):
        self.b.exec("UPDATE colaborador SET optout_em=NULL WHERE id=?", (id_,))

    def atualizar_resumo(self, id_, resumo):
        self.b.exec("UPDATE colaborador SET resumo_contexto=? WHERE id=?", (resumo, id_))

    # ---- mensagens e análises ----
    def salvar_mensagem(self, colab_id, direcao, origem, texto, transcricao, dia, quando):
        return self.b.exec(
            "INSERT INTO mensagem(colaborador_id, direcao, origem, texto, transcricao, dia_jornada, criada_em)"
            " VALUES (?,?,?,?,?,?,?)", (colab_id, direcao, origem, texto, transcricao, dia, quando)).lastrowid

    def tem_mensagem_saida(self, colab_id):
        return self.b.um("SELECT 1 FROM mensagem WHERE colaborador_id=? AND direcao='SAIDA' LIMIT 1", (colab_id,)) is not None

    def ultimas_mensagens(self, colab_id, n=6):
        rows = self.b.todos("SELECT direcao, texto, transcricao FROM mensagem WHERE colaborador_id=? ORDER BY id DESC LIMIT ?",
                            (colab_id, n))
        return [("colaborador" if r["direcao"] == "ENTRADA" else "assistente", r["transcricao"] or r["texto"] or "")
                for r in reversed(rows)]

    def salvar_analise(self, mensagem_id, a):
        return self.b.exec(
            "INSERT INTO analise(mensagem_id, intencao, categoria, sinal, gravidade, alvo, destinatario, confianca,"
            " resposta, origem_analise, escalado_por_regra) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (mensagem_id, a.intencao.value, a.categoria.value, a.sinal.value, a.gravidade.value, a.alvo.value,
             a.destinatario.value, a.confianca, a.resposta, a.origem_analise, int(a.escalado_por_regra))).lastrowid

    # ---- cadência, pílulas e enquetes ----
    def colaboradores_para_cadencia(self):
        rows = self.b.todos("SELECT * FROM colaborador WHERE papel='COLABORADOR' AND ativo=1"
                            " AND consentimento_em IS NOT NULL AND optout_em IS NULL ORDER BY id")
        return [_obj(r) for r in rows]

    def envio_existe(self, colab_id, dia):
        return self.b.um("SELECT 1 FROM envio WHERE colaborador_id=? AND dia=?", (colab_id, dia)) is not None

    def registrar_envio(self, colab_id, dia, tipo, ref, quando):
        cur = self.b.exec("INSERT OR IGNORE INTO envio(colaborador_id, dia, tipo, ref, enviado_em) VALUES (?,?,?,?,?)",
                          (colab_id, dia, tipo, ref, quando))
        return cur.rowcount > 0

    def refs_enviadas(self, colab_id, tipo):
        return {r["ref"] for r in self.b.todos("SELECT ref FROM envio WHERE colaborador_id=? AND tipo=?", (colab_id, tipo))}

    def concluir_envio(self, colab_id, tipo, ref, quando):
        self.b.exec("UPDATE envio SET concluido_em=? WHERE colaborador_id=? AND tipo=? AND ref=? AND concluido_em IS NULL",
                    (quando, colab_id, tipo, ref))

    def salvar_resposta_enquete(self, enquete_id, colab_id, opcao_id, rotulo, dia, quando):
        self.b.exec("INSERT INTO enquete_resposta(enquete_id, colaborador_id, opcao_id, rotulo, dia_jornada, criada_em)"
                    " VALUES (?,?,?,?,?,?)", (enquete_id, colab_id, opcao_id, rotulo, dia, quando))

    def contar_respostas_enquete(self):
        rows = self.b.todos("SELECT enquete_id, opcao_id, COUNT(*) AS n FROM enquete_resposta GROUP BY enquete_id, opcao_id")
        return [dict(r) for r in rows]

    # ---- alertas ----
    def criar_alerta(self, colaborador_id, analise_id, canal, sinal, gravidade, sugestao, resumo, estado, quando):
        return self.b.exec(
            "INSERT INTO alerta(colaborador_id, analise_id, canal, sinal, gravidade, sugestao, resumo, estado, criado_em)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (colaborador_id, analise_id, canal, sinal, gravidade, sugestao, resumo, estado, quando)).lastrowid

    def alerta(self, id_):
        return _obj(self.b.um("SELECT * FROM alerta WHERE id=?", (id_,)))

    def alerta_pendente(self, colaborador_id):
        return _obj(self.b.um("SELECT * FROM alerta WHERE colaborador_id=? AND estado='AGUARDANDO_CONFIRMACAO'"
                              " ORDER BY id DESC LIMIT 1", (colaborador_id,)))

    def atualizar_alerta(self, id_, **campos):
        if not campos or not set(campos) <= _CAMPOS_ALERTA:
            raise ValueError(f"campos inválidos: {set(campos) - _CAMPOS_ALERTA}")
        sets = ", ".join(f"{k}=?" for k in campos)
        self.b.exec(f"UPDATE alerta SET {sets} WHERE id=?", (*campos.values(), id_))

    def descartar_pendentes(self, colaborador_id):
        self.b.exec("UPDATE alerta SET estado='SO_CONTEXTO' WHERE colaborador_id=? AND estado='AGUARDANDO_CONFIRMACAO'",
                    (colaborador_id,))

    def alertas_para_lembrar(self, agora):
        rows = self.b.todos("SELECT * FROM alerta WHERE estado='ABERTO' AND lembrete_em IS NOT NULL"
                            " AND lembrete_em<=? AND lembrado_em IS NULL", (agora,))
        return [_obj(r) for r in rows]

    def contar_alertas(self):
        return {r["estado"]: r["n"] for r in self.b.todos("SELECT estado, COUNT(*) AS n FROM alerta GROUP BY estado")}
