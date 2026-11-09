import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.analisador import Analisador
from app.seed import popular, popular_demo
from app.services.conteudo import Conteudo
from app.services.conversa import Conversa
from app.services.painel import Conflito, Painel
from app.services.relogio import Relogio
from app.storage.db import Banco
from app.storage.repositorio import Repositorio
from tests.test_fluxo import LLMRoteirizado

ANA, MARCOS = "5551999990001", "5551999990002"


class Base(unittest.TestCase):
    demo = True

    def setUp(self):
        banco = Banco()
        self.repo, self.relogio = Repositorio(banco), Relogio(banco)
        popular(self.repo, self.relogio)
        if self.demo:
            popular_demo(self.repo, self.relogio)
        conteudo = Conteudo.carregar()
        self.painel = Painel(self.repo, self.relogio, conteudo)
        self.conversa = Conversa(self.repo, Analisador(LLMRoteirizado(), "", "{{contexto}}{{faq}}"), self.relogio, conteudo)

    def id_de(self, nome):
        return self.repo.b.um("SELECT id FROM colaborador WHERE nome=?", (nome,))["id"]

    def jornada(self, nome):
        return next(j for j in self.painel.dashboard()["journeys"] if j["employeeName"] == nome)


class TestDashboard(Base):
    def test_cards(self):
        r = self.painel.dashboard()["summary"]
        self.assertEqual(r, {"inJourney": 7, "openAlerts": 5, "noResponse": 1, "attended": 5})

    def test_status_de_cada_jornada(self):
        esperado = {"João Silva": "open-alert", "Lucas Martins": "no-response", "Bianca Rocha": "attended",
                    "Pedro Alves": "on-track", "Ana Pereira": "pending"}
        for nome, status in esperado.items():
            self.assertEqual(self.jornada(nome)["status"], status, nome)
        self.assertEqual(self.jornada("Ana Pereira")["statusLabel"], "Aguardando aceite")

    def test_jornadas_mostram_mentor_e_gerente(self):
        j = self.jornada("João Silva")
        self.assertEqual((j["mentor"], j["manager"], j["totalDays"]), ("Rafael Mendes", "Marcos Lima", 90))
        self.assertIsNone(self.jornada("Lucas Martins")["mentor"])

    def test_so_colaboradores_em_jornada(self):
        nomes = {j["employeeName"] for j in self.painel.dashboard()["journeys"]}
        self.assertNotIn("Marcos Lima", nomes)
        self.assertNotIn("Rafael Mendes", nomes)

    def test_resumo_do_alerta_so_no_canal_rh(self):
        alertas = {a["employeeName"]: a for a in self.painel.dashboard()["alerts"] if a["state"] != "Atendido"}
        self.assertIsNone(alertas["João Silva"]["summary"])
        self.assertIn("humilhante", alertas["Carla Dias"]["summary"])
        self.assertEqual(alertas["Carla Dias"]["channel"], "RH")

    def test_alertas_ordenados_por_urgencia(self):
        cats = [a["category"] for a in self.painel.dashboard()["alerts"]]
        self.assertEqual(cats[0], "no-response")
        self.assertEqual(cats, sorted(cats, key=lambda c: {"no-response": 0, "not-reached": 1, "open": 2, "attended": 3}[c]))

    def test_alerta_nao_confirmado_nao_aparece_para_o_rh(self):
        antes = len(self.painel.dashboard()["alerts"])
        self.conversa.boas_vindas_se_preciso(ANA)
        self.conversa.processar_escolha(ANA, "ACEITO")
        self.conversa.processar_texto(ANA, "estou muito cansado")  # fica aguardando a confirmação
        self.assertEqual(len(self.painel.dashboard()["alerts"]), antes)
        self.conversa.processar_escolha(ANA, "AVISAR")
        self.assertEqual(len(self.painel.dashboard()["alerts"]), antes + 1)

    def test_retorno_do_lider_atualiza_o_painel(self):
        self.conversa.boas_vindas_se_preciso(ANA)
        self.conversa.processar_escolha(ANA, "ACEITO")
        self.conversa.processar_texto(ANA, "estou muito cansado")
        msg = next(s for s in self.conversa.processar_escolha(ANA, "AVISAR") if s.alerta_id)
        self.assertEqual(self.jornada("Ana Pereira")["status"], "open-alert")
        self.conversa.registrar_retorno(msg.alerta_id, "CONVERSEI")
        self.assertEqual(self.jornada("Ana Pereira")["status"], "attended")

    def test_sem_resposta_vira_vermelho_depois_de_24h(self):
        self.conversa.boas_vindas_se_preciso(ANA)
        self.conversa.processar_escolha(ANA, "ACEITO")
        self.conversa.processar_texto(ANA, "estou muito cansado")
        self.conversa.processar_escolha(ANA, "AVISAR")
        self.relogio.avancar(25)
        self.conversa.processar_lembretes()
        self.assertEqual(self.jornada("Ana Pereira")["status"], "no-response")


class TestLembreteManual(Base):
    def test_reenvia_para_o_gerente_e_nao_duplica_o_automatico(self):
        alerta = next(a for a in self.painel.dashboard()["alerts"] if a["employeeName"] == "João Silva" and a["category"] == "open")
        saidas = self.conversa.reenviar_lembrete(alerta["id"])
        self.assertEqual([s.para for s in saidas], ["5551999990002"])
        self.assertIn("Lembrete", saidas[0].texto)
        self.relogio.avancar(48)
        self.assertEqual([s for s in self.conversa.processar_lembretes() if s.alerta_id == alerta["id"]], [])

    def test_alerta_encerrado_ou_inexistente(self):
        atendido = next(a for a in self.painel.dashboard()["alerts"] if a["category"] == "attended")
        with self.assertRaises(ValueError):
            self.conversa.reenviar_lembrete(atendido["id"])
        with self.assertRaises(LookupError):
            self.conversa.reenviar_lembrete(9999)


class TestColaboradores(Base):
    demo = False

    def novo(self, **kw):
        loja = self.painel.lojas()[0]["id"]
        dados = {"nome": "Teste Silva", "telefone": "(51) 98888-7777", "lojaId": loja, "dataEntrada": self.relogio.agora().strftime("%Y-%m-%d")}
        dados.update(kw)
        return self.painel.criar_colaborador(dados)

    def test_cria_normaliza_telefone_e_define_gerente_da_loja(self):
        c = self.novo(lojaId=self.repo.criar_loja("Porto Alegre"))
        self.assertEqual(c["telefone"], "5551988887777")
        self.assertEqual(c["gerente"], "Marcos Lima")
        self.assertEqual(c["dia"], 1)
        self.assertFalse(c["aceitou"])

    def test_validacoes(self):
        casos = [({"nome": " "}, "nome"), ({"telefone": "123"}, "Telefone"), ({"lojaId": None}, "loja"),
                 ({"lojaId": 999}, "Loja"), ({"dataEntrada": ""}, "data"), ({"papel": "CHEFE"}, "Papel"),
                 ({"dataEntrada": (self.relogio.agora() + timedelta(days=3)).strftime("%Y-%m-%d")}, "futuro"),
                 ({"gerenteId": self.id_de("Ana Pereira")}, "gerente")]
        for extra, trecho in casos:
            with self.assertRaises(ValueError, msg=str(extra)) as ctx:
                self.novo(**extra)
            self.assertIn(trecho.lower(), str(ctx.exception).lower())

    def test_telefone_repetido_e_conflito(self):
        self.novo()
        with self.assertRaises(Conflito):
            self.novo(nome="Outra Pessoa")

    def test_novo_colaborador_recebe_as_boas_vindas(self):
        c = self.novo()
        s = self.conversa.boas_vindas_se_preciso(c["telefone"])
        self.assertIn("Parceiro dos 90 dias", s[0].texto)

    def test_desativar_encerra_mentoria_e_some_da_jornada(self):
        aprendiz = self.novo(nome="Aprendiz Teste", telefone="51977776666")
        mentor = self.novo(nome="Mentor Teste", telefone="51966665555", papel="MENTOR", dataEntrada=None)
        self.painel.vincular(mentor["id"], aprendiz["id"])
        self.painel.atualizar_colaborador(aprendiz["id"], {"ativo": False})
        self.assertEqual(self.painel.mentorias()["vinculos"], [])
        self.assertNotIn("Aprendiz Teste", {j["employeeName"] for j in self.painel.dashboard()["journeys"]})

    def test_atualiza_gerente_e_loja(self):
        c = self.novo()
        gerente = self.id_de("Juliana Nunes")
        r = self.painel.atualizar_colaborador(c["id"], {"gerenteId": gerente})
        self.assertEqual(r["gerente"], "Juliana Nunes")
        with self.assertRaises(LookupError):
            self.painel.atualizar_colaborador(9999, {"nome": "x"})


class TestMentoria(Base):
    def test_lista_vinculos_e_quem_esta_sem_mentor(self):
        m = self.painel.mentorias()
        self.assertEqual({(v["mentor"], v["aprendiz"]) for v in m["vinculos"]},
                         {("Rafael Mendes", "João Silva"), ("Rafael Mendes", "Pedro Alves"),
                          ("Camila Torres", "Carla Dias"), ("Camila Torres", "Rafael Souza")})
        self.assertIn("Lucas Martins", {s["nome"] for s in m["semMentor"]})
        self.assertEqual({x["nome"]: x["aprendizes"] for x in m["mentores"]}, {"Rafael Mendes": 2, "Camila Torres": 2})

    def test_trocar_de_mentor_encerra_o_vinculo_anterior(self):
        joao, camila = self.id_de("João Silva"), self.id_de("Camila Torres")
        m = self.painel.vincular(camila, joao)
        self.assertEqual([v["mentor"] for v in m["vinculos"] if v["aprendiz"] == "João Silva"], ["Camila Torres"])

    def test_papeis_validos(self):
        with self.assertRaises(ValueError):
            self.painel.vincular(self.id_de("Marcos Lima"), self.id_de("João Silva"))  # gerente não é mentor
        with self.assertRaises(ValueError):
            self.painel.vincular(self.id_de("Rafael Mendes"), self.id_de("Camila Torres"))  # mentor não é aprendiz

    def test_encerrar(self):
        v = self.painel.mentorias()["vinculos"][0]
        self.painel.encerrar_mentoria(v["id"])
        self.assertNotIn(v["id"], [x["id"] for x in self.painel.mentorias()["vinculos"]])
        with self.assertRaises(LookupError):
            self.painel.encerrar_mentoria(v["id"])


class TestInsights(Base):
    def test_metricas_do_desafio(self):
        i = self.painel.insights()
        self.assertEqual(i["taxaResposta10Dias"], {"valor": 71, "meta": 50, "base": 7})
        self.assertIsNotNone(i["tempoMedioRetornoHoras"])
        self.assertTrue(0 <= i["atendidosEm24hPct"] <= 100)
        self.assertEqual(i["totalAlertas"], 10)

    def test_alertas_por_semana_e_por_tipo(self):
        i = self.painel.insights()
        self.assertEqual(len(i["alertasPorSemana"]), 6)
        self.assertGreater(i["alertasPorSemana"][-1]["total"], 0)  # alertas de hoje na semana atual
        self.assertEqual(sum(s["n"] for s in i["sinais"]), 10)

    def test_divergencia_entre_curso_e_loja(self):
        t = self.painel.insights()["treinamento"]
        self.assertEqual(t, {"total": 7, "bate": 1, "emParte": 2, "diferente": 3, "semCurso": 1})

    def test_enquetes_agregadas_com_percentual(self):
        e = next(x for x in self.painel.insights()["enquetes"] if x["id"] == "bem-estar")
        self.assertEqual(e["total"], 7)
        self.assertEqual(sum(o["n"] for o in e["opcoes"]), 7)
        self.assertEqual(next(o for o in e["opcoes"] if o["id"] == "bem")["pct"], 57)

    def test_mentoria_no_insight(self):
        self.assertEqual(self.painel.insights()["mentoria"]["comMentor"], 4)

    def test_painel_vazio_nao_quebra(self):
        banco = Banco()
        repo, relogio = Repositorio(banco), Relogio(banco)
        painel = Painel(repo, relogio, Conteudo.carregar())
        i = painel.insights()
        self.assertIsNone(i["taxaResposta10Dias"]["valor"])
        self.assertEqual(painel.dashboard()["summary"], {"inJourney": 0, "openAlerts": 0, "noResponse": 0, "attended": 0})


if __name__ == "__main__":
    unittest.main()
