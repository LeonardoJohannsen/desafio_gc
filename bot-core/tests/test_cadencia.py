import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.analisador import Analisador
from app.seed import popular
from app.services import jornada
from app.services.cadencia import Cadencia
from app.services.conteudo import Conteudo
from app.services.conversa import Conversa
from app.services.relogio import Relogio
from app.storage.db import Banco
from app.storage.repositorio import Repositorio
from tests.test_fluxo import LLMRoteirizado

ANA, MARCOS = "5551999990001", "5551999990002"


class TestAgenda(unittest.TestCase):
    def test_primeiros_10_dias_todo_dia(self):
        self.assertTrue(all(jornada.tipo_do_dia(d) for d in range(1, 11)))

    def test_depois_vai_espacando(self):
        self.assertIsNone(jornada.tipo_do_dia(11))
        self.assertIsNone(jornada.tipo_do_dia(12))
        self.assertIsNotNone(jornada.tipo_do_dia(13))
        self.assertIsNone(jornada.tipo_do_dia(31))
        self.assertIsNotNone(jornada.tipo_do_dia(37))
        self.assertIsNotNone(jornada.tipo_do_dia(70))

    def test_marcos_da_agenda_da_empresa(self):
        for dia in (7, 15, 30, 45, 60, 90):
            self.assertEqual(jornada.tipo_do_dia(dia), "MARCO")

    def test_pilulas_sao_minoria(self):
        tipos = list(jornada.AGENDA.values())
        self.assertLess(tipos.count("PILULA"), len(tipos) / 3)
        self.assertEqual(jornada.tipo_do_dia(2), "PILULA")
        self.assertEqual(jornada.tipo_do_dia(10), "ENQUETE")
        self.assertEqual(max(jornada.AGENDA), 90)

    def test_conteudo_minimo_do_desafio(self):
        c = Conteudo.carregar()
        self.assertGreaterEqual(len(c.pilulas), 5)
        for p in c.pilulas:
            self.assertTrue(p["texto"].strip().endswith("?"), p["id"])  # toda pílula puxa conversa
            self.assertLess(len(p["texto"].split()), 70, p["id"])  # ~30 segundos de leitura


class Base(unittest.TestCase):
    def setUp(self):
        banco = Banco()
        self.repo, self.relogio = Repositorio(banco), Relogio(banco)
        popular(self.repo, self.relogio)
        self.conteudo = Conteudo.carregar()
        analisador = Analisador(LLMRoteirizado(), faq="", template="{{contexto}}{{faq}}")
        self.c = Conversa(self.repo, analisador, self.relogio, self.conteudo)
        self.cad = Cadencia(self.repo, self.c, self.relogio, self.conteudo)
        self.c.boas_vindas_se_preciso(ANA)
        self.c.processar_escolha(ANA, "ACEITO")  # Ana no dia 6

    def avancar_dia(self):
        self.relogio.avancar(24)
        return self.cad.executar(ignorar_horario=True)

    def de(self, saidas, tel):
        return [s for s in saidas if s.para == tel]


class TestCadencia(Base):
    def test_no_dia_do_aceite_nao_repete(self):
        ana = [s for s in self.cad.executar(True) if s.para == ANA]
        self.assertEqual(ana, [])

    def test_so_quem_aceitou_recebe(self):
        outra = Base.__new__(Base)
        banco = Banco(); repo = Repositorio(banco); relogio = Relogio(banco); popular(repo, relogio)
        cad = Cadencia(repo, Conversa(repo, Analisador(LLMRoteirizado(), "", ""), relogio), relogio, Conteudo.carregar())
        self.assertNotIn(ANA, {s.para for s in cad.executar(True)})  # Ana ainda não aceitou

    def test_dia_7_marco_para_ana_e_aviso_ao_gerente(self):
        s = self.avancar_dia()
        self.assertIn("1 semana", self.de(s, ANA)[0].texto)
        self.assertIn("completa 7 dias", self.de(s, MARCOS)[0].texto)

    def test_nao_duplica_no_mesmo_dia(self):
        self.avancar_dia()
        self.assertEqual(self.cad.executar(True), [])

    def test_dia_8_pilula_com_botoes_e_conclusao(self):
        self.avancar_dia()
        ana = self.de(self.avancar_dia(), ANA)[0]
        self.assertIn("Pílula de 30 segundos", ana.texto)
        ids = [o["id"] for o in ana.opcoes]
        self.assertTrue(ids[0].startswith("PIL:") and ids[0].endswith(":OK"))
        self.c.processar_escolha(ANA, ids[0])
        ref = ids[0].split(":")[1]
        ana_id = self.repo.colaborador_por_telefone(ANA).id
        row = self.repo.b.um("SELECT concluido_em FROM envio WHERE colaborador_id=? AND tipo='PILULA' AND ref=?", (ana_id, ref))
        self.assertIsNotNone(row["concluido_em"])

    def test_pilula_com_duvida_convida_a_perguntar(self):
        self.avancar_dia()
        ana = self.de(self.avancar_dia(), ANA)[0]
        r = self.c.processar_escolha(ANA, ana.opcoes[1]["id"])
        self.assertIn("dúvida", r[0].texto)

    def test_pilulas_nao_repetem(self):
        enviadas = []
        for _ in range(60):
            for s in self.de(self.avancar_dia(), ANA):
                if s.texto.startswith("💡"):
                    enviadas.append(s.texto)
        self.assertEqual(len(enviadas), len(set(enviadas)))
        self.assertGreaterEqual(len(enviadas), 5)

    def test_fora_do_horario_nao_envia(self):
        h = self.relogio.agora().hour
        fechada = Cadencia(self.repo, self.c, self.relogio, self.conteudo, hora_inicio=h + 1, hora_fim=h + 2)
        self.relogio.avancar(24)
        self.assertEqual(fechada.executar(), [])
        self.assertTrue(fechada.executar(ignorar_horario=True))

    def test_quem_pausou_nao_recebe(self):
        self.c.processar_texto(ANA, "parar")
        self.assertEqual(self.de(self.avancar_dia(), ANA), [])


class TestEnquetes(Base):
    def chegar_ao_dia_10(self):
        saidas = []
        for _ in range(4):
            saidas = self.avancar_dia()
        return self.de(saidas, ANA)[0]

    def test_dia_10_enquete_com_botoes(self):
        e = self.chegar_ao_dia_10()
        self.assertIn("Como você está se sentindo", e.texto)
        self.assertEqual(len(e.opcoes), 3)
        self.assertTrue(e.opcoes[0]["id"].startswith("ENQ:bem-estar:"))

    def test_resposta_comum_e_registrada_sem_alerta(self):
        e = self.chegar_ao_dia_10()
        r = self.c.processar_escolha(ANA, e.opcoes[0]["id"])
        self.assertEqual(len(r), 1)
        self.assertEqual(self.repo.contar_respostas_enquete(), [{"enquete_id": "bem-estar", "opcao_id": "bem", "n": 1}])
        self.assertEqual(self.repo.contar_alertas(), {})

    def test_resposta_dificil_pede_confirmacao_e_depois_avisa_o_gerente(self):
        e = self.chegar_ao_dia_10()
        r = self.c.processar_escolha(ANA, e.opcoes[2]["id"])
        self.assertEqual([o["id"] for o in r[0].opcoes], ["AVISAR", "NAO_AVISAR"])
        self.assertEqual(self.repo.contar_alertas(), {"AGUARDANDO_CONFIRMACAO": 1})
        out = self.c.processar_escolha(ANA, "AVISAR")
        alerta = next(s for s in out if s.alerta_id)
        self.assertEqual(alerta.para, MARCOS)
        self.assertIn("Está difícil", alerta.texto)

    def test_opcao_invalida_e_ignorada(self):
        self.assertEqual(self.c.processar_escolha(ANA, "ENQ:nao-existe:x"), [])
        self.assertEqual(self.c.processar_escolha(ANA, "ENQ:bem-estar"), [])


if __name__ == "__main__":
    unittest.main()
